import 'package:flutter/widgets.dart';
import 'package:google_fonts/google_fonts.dart';

/// Text styles matching the design's three-font system:
/// Space Grotesk (amounts/headlines), Instrument Sans (body), IBM Plex Mono
/// (micro labels / meta / tabular data). Colors are applied at the call site
/// (AppColors.onDark / AppColors.onLight / semantic colors) since the same
/// role is reused on both dark and light surfaces.
abstract final class AppTypography {
  // Space Grotesk - hero amounts & headlines
  static TextStyle heroAmount44 = GoogleFonts.spaceGrotesk(
    fontSize: 44,
    fontWeight: FontWeight.w700,
    height: 1,
    letterSpacing: -0.03 * 44,
  );
  static TextStyle heroAmount40 = GoogleFonts.spaceGrotesk(
    fontSize: 40,
    fontWeight: FontWeight.w700,
    height: 1,
    letterSpacing: -0.03 * 40,
  );
  static TextStyle heroAmount36 = GoogleFonts.spaceGrotesk(
    fontSize: 36,
    fontWeight: FontWeight.w700,
    height: 1,
    letterSpacing: -0.02 * 36,
  );
  static TextStyle heroAmount34 = GoogleFonts.spaceGrotesk(
    fontSize: 34,
    fontWeight: FontWeight.w700,
    height: 1,
  );
  static TextStyle screenTitle24 = GoogleFonts.spaceGrotesk(
    fontSize: 24,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.02 * 24,
  );
  static TextStyle navTitle15 = GoogleFonts.spaceGrotesk(
    fontSize: 15,
    fontWeight: FontWeight.w600,
  );
  static TextStyle bigHeadline32 = GoogleFonts.spaceGrotesk(
    fontSize: 32,
    fontWeight: FontWeight.w700,
    height: 1.2,
    letterSpacing: -0.03 * 32,
  );
  static TextStyle bigHeadline26 = GoogleFonts.spaceGrotesk(
    fontSize: 26,
    fontWeight: FontWeight.w700,
    height: 1.25,
    letterSpacing: -0.02 * 26,
  );
  static TextStyle bigHeadline22 = GoogleFonts.spaceGrotesk(
    fontSize: 22,
    fontWeight: FontWeight.w700,
    height: 1.3,
    letterSpacing: -0.02 * 22,
  );
  static TextStyle amountMedium20 = GoogleFonts.spaceGrotesk(fontSize: 20, fontWeight: FontWeight.w600);
  static TextStyle amountMedium19 = GoogleFonts.spaceGrotesk(fontSize: 19, fontWeight: FontWeight.w700);
  static TextStyle amountMedium17 = GoogleFonts.spaceGrotesk(fontSize: 17, fontWeight: FontWeight.w600);
  static TextStyle amountMedium16 = GoogleFonts.spaceGrotesk(fontSize: 16, fontWeight: FontWeight.w600);
  static TextStyle amountMedium15 = GoogleFonts.spaceGrotesk(fontSize: 15, fontWeight: FontWeight.w600);
  static TextStyle amountMedium14 = GoogleFonts.spaceGrotesk(fontSize: 14, fontWeight: FontWeight.w600);
  static TextStyle amountSmall22 = GoogleFonts.spaceGrotesk(fontSize: 22, fontWeight: FontWeight.w700);
  static TextStyle wordmark14 = GoogleFonts.spaceGrotesk(fontSize: 14, fontWeight: FontWeight.w600);

  // Instrument Sans - body copy
  static TextStyle signalBody17 = GoogleFonts.instrumentSans(fontSize: 17, fontWeight: FontWeight.w500, height: 1.45);
  static TextStyle cardBody15 = GoogleFonts.instrumentSans(fontSize: 15, fontWeight: FontWeight.w500, height: 1.45);
  static TextStyle cardBody135 = GoogleFonts.instrumentSans(fontSize: 13.5, fontWeight: FontWeight.w500, height: 1.5);
  static TextStyle body14 = GoogleFonts.instrumentSans(fontSize: 14, fontWeight: FontWeight.w500);
  static TextStyle body13 = GoogleFonts.instrumentSans(fontSize: 13, fontWeight: FontWeight.w500, height: 1.5);
  static TextStyle rowLabel145 = GoogleFonts.instrumentSans(fontSize: 14.5, fontWeight: FontWeight.w600);
  static TextStyle rowLabel14 = GoogleFonts.instrumentSans(fontSize: 14, fontWeight: FontWeight.w600);
  static TextStyle buttonLabel15 = GoogleFonts.instrumentSans(fontSize: 15, fontWeight: FontWeight.w600);
  static TextStyle buttonLabel14 = GoogleFonts.instrumentSans(fontSize: 14, fontWeight: FontWeight.w600);
  static TextStyle buttonLabel12 = GoogleFonts.instrumentSans(fontSize: 12, fontWeight: FontWeight.w600);
  static TextStyle buttonLabel13 = GoogleFonts.instrumentSans(fontSize: 13, fontWeight: FontWeight.w600);
  static TextStyle footnote1155 = GoogleFonts.instrumentSans(fontSize: 11.5, fontWeight: FontWeight.w400, height: 1.5);
  static TextStyle footnote12 = GoogleFonts.instrumentSans(fontSize: 12, fontWeight: FontWeight.w400, height: 1.45);
  static TextStyle footnote15 = GoogleFonts.instrumentSans(fontSize: 15, fontWeight: FontWeight.w400, height: 1.55);

  // IBM Plex Mono - micro labels / meta / tabular data
  static TextStyle microLabel11 = GoogleFonts.ibmPlexMono(fontSize: 11, fontWeight: FontWeight.w500, letterSpacing: 0.1 * 11);
  static TextStyle microLabelTracked105 =
      GoogleFonts.ibmPlexMono(fontSize: 10.5, fontWeight: FontWeight.w600, letterSpacing: 0.1 * 10.5);
  static TextStyle microLabelTracked11 =
      GoogleFonts.ibmPlexMono(fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 0.12 * 11);
  static TextStyle meta115 = GoogleFonts.ibmPlexMono(fontSize: 11.5, fontWeight: FontWeight.w500);
  static TextStyle meta12 = GoogleFonts.ibmPlexMono(fontSize: 12, fontWeight: FontWeight.w500);
  static TextStyle metaBold12 = GoogleFonts.ibmPlexMono(fontSize: 12, fontWeight: FontWeight.w600);
  static TextStyle badge95 = GoogleFonts.ibmPlexMono(fontSize: 9.5, fontWeight: FontWeight.w600);
  static TextStyle badge10 = GoogleFonts.ibmPlexMono(fontSize: 10, fontWeight: FontWeight.w600);
}
