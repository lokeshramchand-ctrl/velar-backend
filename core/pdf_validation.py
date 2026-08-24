import logging
from enum import Enum

logger = logging.getLogger(__name__)

PDF_MAGIC_BYTES = b"%PDF"
PDF_SIGNATURE_OFFSET = 0
GOOGLE_PAY_IDENTIFIER = "UPI Transaction ID"

class PDFValidationError(Exception):
    """Raised when PDF validation fails."""
    pass


class PDFValidationType(str, Enum):
    MAGIC_BYTES = "magic_bytes"
    MIME_TYPE = "mime_type"
    SIGNATURE = "signature"
    SIZE = "size"


def validate_pdf_magic_bytes(data: bytes) -> bool:
    """Validate PDF magic bytes (file signature).

    PDFs must start with %PDF magic bytes at offset 0.
    Returns True if valid, raises PDFValidationError if invalid.
    """
    if len(data) < 4:
        raise PDFValidationError(
            f"PDF file too small ({len(data)} bytes). Minimum 4 bytes required for magic bytes check."
        )

    if not data.startswith(PDF_MAGIC_BYTES):
        raise PDFValidationError(
            "Invalid PDF magic bytes. File does not start with '%PDF' signature."
        )

    return True


def validate_pdf_mime_type(content_type: str | None) -> bool:
    """Validate PDF MIME type.

    Accepts application/pdf, application/x-pdf.
    """
    if not content_type:
        logger.warning("No Content-Type header provided for PDF validation")
        return False

    valid_mime_types = ["application/pdf", "application/x-pdf"]
    if content_type.lower() not in valid_mime_types:
        raise PDFValidationError(
            f"Invalid MIME type: {content_type}. Expected application/pdf or application/x-pdf"
        )

    return True


def validate_google_pay_statement(data: bytes) -> bool:
    """Verify PDF contains Google Pay statement indicators.

    Looks for UPI Transaction ID marker to confirm it's a Google Pay statement.
    """
    try:
        if GOOGLE_PAY_IDENTIFIER.encode() not in data:
            raise PDFValidationError(
                "PDF does not appear to be a Google Pay statement. "
                "Missing 'UPI Transaction ID' identifier."
            )
        return True
    except Exception as e:
        raise PDFValidationError(f"Error validating Google Pay statement: {str(e)}") from e


def validate_pdf_integrity(data: bytes) -> bool:
    """Perform basic PDF integrity checks.

    Checks for:
    - Valid magic bytes
    - Proper EOF marker or xref table
    """
    validate_pdf_magic_bytes(data)

    if not (b"%%EOF" in data or b"xref" in data):
        logger.warning("PDF missing EOF marker and xref table. May be incomplete.")

    return True


def validate_pdf_upload(
    data: bytes,
    content_type: str | None = None,
    filename: str | None = None,
    max_size: int = 10_000_000,
) -> dict[str, bool]:
    """Comprehensive PDF validation before processing.

    Args:
        data: PDF file bytes
        content_type: MIME type from Content-Type header
        filename: Original filename
        max_size: Maximum allowed file size in bytes

    Returns:
        Dict with validation results for each check

    Raises:
        PDFValidationError: If any validation fails
    """
    results = {}

    if len(data) > max_size:
        raise PDFValidationError(
            f"PDF file size ({len(data)} bytes) exceeds maximum allowed size ({max_size} bytes)"
        )
    results[PDFValidationType.SIZE] = True

    if not validate_pdf_magic_bytes(data):
        raise PDFValidationError("Invalid PDF magic bytes")
    results[PDFValidationType.MAGIC_BYTES] = True

    if content_type:
        try:
            if not validate_pdf_mime_type(content_type):
                raise PDFValidationError("Invalid MIME type")
            results[PDFValidationType.MIME_TYPE] = True
        except PDFValidationError:
            results[PDFValidationType.MIME_TYPE] = False
            raise
    else:
        results[PDFValidationType.MIME_TYPE] = None

    if filename and filename.lower().endswith(".pdf"):
        try:
            if not validate_pdf_integrity(data):
                raise PDFValidationError("PDF integrity check failed")
            results[PDFValidationType.SIGNATURE] = True
        except PDFValidationError:
            results[PDFValidationType.SIGNATURE] = False
            raise

    return results
