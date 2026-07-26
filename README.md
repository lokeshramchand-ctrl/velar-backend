Velar Transaction Intelligence EngineVelar is a production-grade machine learning backend designed to transform raw, noisy financial transaction strings into structured behavioral intelligence.Rather than relying on basic string matching or a single monolithic LLM, Velar operates on a 15-phase pipeline. It combines deterministic rule engines, a stateful memory system, statistical baselines, and a Retrieval-Augmented Generation (RAG) layer to provide explainable, hallucination-free analytics.Tech StackFramework: FastAPILanguages: Python 3.10+Primary Database (Ledger & State): MongoDBVector Database (Semantic Search): MilvusMachine Learning: Scikit-learn, LightGBM, XGBoost, SHAPLLM Integration: Local Ollama (or equivalent HTTP inference endpoints)Observability: Prometheus, MLflow, Evidently AIRate Limiting: SlowAPIInstallation and Setup1. Environment PreparationEnsure Python 3.10 or higher is installed. Create and activate a virtual environment:python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
2. Install DependenciesInstall the required packages using the provided requirements file:pip install -r requirements.txt
3. Infrastructure setupVelar requires MongoDB and Milvus. You can spin these up locally using Docker. Create a docker-compose.yml file in your root directory:version: '3.8'
services:
  mongodb:
    image: mongo:latest
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db

  milvus-standalone:
    image: milvusdb/milvus:v2.4.0
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_USE_EMBED: "true"
      ETCD_DATA_DIR: "/var/lib/milvus/etcd"
    ports:
      - "19530:19530"
      - "9091:9091"
    volumes:
      - milvus_data:/var/lib/milvus

volumes:
  mongo_data:
  milvus_data:
Run the containers:docker-compose up -d
4. Environment VariablesCreate a .env file in the backend/ directory:MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=velar
MILVUS_HOST=localhost
MILVUS_PORT=19530
5. Start the ServerRun the FastAPI application via Uvicorn:uvicorn app:app --reload --host 0.0.0.0 --port 8080
API Endpoints DetailedThe following endpoints outline the core capabilities of the Velar engine. All public-facing endpoints require the X-Velar-API-Key header for authorization.Ingestion & Resolution (Phase 1-3)POST /v1/categorizeDescription: The deterministic rule engine. Processes raw text against a predefined dictionary.Payload: {"text": "paid 500 to swiggy"}Response: Returns merchant, category, and a confidence score.POST /v1/resolveDescription: Cleans noisy banking data (e.g., UPI/CR/...) using regex patterns and maps it to a canonical merchant alias.Payload: {"text": "UPI/CR/3152671239/BUNDL TECHNOLOGIES/HDFC"}Memory Engine (Phase 4)POST /memory/updateDescription: Updates the state machine for a merchant. Promotes a merchant through EPHEMERAL, TEMPORARY, and PERMANENT states based on interaction frequency.Payload: {"canonical_name": "Zomato", "raw_text": "paid to zomato"}Confidence Wall (Phase 5)POST /v1/confidence/evaluateDescription: Evaluates predictions from the ML pipeline. If a prediction falls below the configured threshold (e.g., 0.50), it overrides the category to "Unknown" to prevent data corruption and hallucination.Payload: {"predicted_category": "Travel", "raw_confidence": 0.40}Analytics Engine (Phase 13)GET /v1/analytics/patterns/categoriesDescription: Aggregates total spending and transaction counts grouped by category over a specified lookback window.Parameters: days (integer, default 30)GET /v1/analytics/patterns/merchantsDescription: Returns the most frequently visited merchants, ranked by transaction count and total spend.Parameters: limit (integer, default 5)GET /v1/analytics/subscriptionsDescription: Uses periodicity scoring to identify recurring transactions and calculates the estimated monthly burn rate for active subscriptions.POST /v1/analytics/anomaly/checkDescription: Real-time evaluation of a transaction amount against the merchant's historical baseline using Z-score (3-Sigma rule) to flag outlier spending.Payload: merchant (string), amount (float)Context RAG & Explainability (Phase 12)POST /v1/explainDescription: Generates a human-readable explanation for a transaction categorization. Queries Milvus for semantic similarity, retrieves structural data from MongoDB, and enforces rigid XML-style prompting to the LLM.Payload: {"transaction_text": "Swiggy order", "target_question": "Why was this categorized this way?"}Observability & MLOps (Phase 14)POST /v1/observability/drift/analyzeDescription: Triggers a background Evidently AI task to compare the current production data distribution against the baseline reference dataset.GET /v1/observability/reports/latestDescription: Serves the generated HTML drift report detailing dataset drift, target drift, and potential embedding degradation.Important Notes & Architecture PrinciplesThe Confidence Wall Principle: "Unknown is a valid answer." Velar is designed to reject low-confidence ML predictions rather than guess. This preserves the integrity of the Analytics and RAG pipelines.The Memory State Machine: Entities are not trusted immediately. A new merchant begins as EPHEMERAL. Repeated interactions promote it to TEMPORARY, and eventually to PERMANENT. Heavy analytics and embedding generations are reserved for PERMANENT entities to optimize compute costs.Grounded RAG: The Explainability layer does not act as a chatbot. It is heavily constrained by system prompts to only synthesize data explicitly provided by the MongoDB/Milvus retriever. If data is absent, it is programmed to return an error rather than hallucinate financial advice.Mock Data Seeding: A script (scripts/mock_seeder.py) is provided to safely inject and clean up realistic transaction data tagged with is_mock: True. This ensures the Analytics Engine can be tested without corrupting production ledgers.Rate Limiting: The application layer is protected by SlowAPI. High-throughput endpoints are throttled based on IP address to prevent abusive traffic spikes from overwhelming the database or LLM inference server.