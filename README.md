# Intelligent Scoring & Validation Service

This project is a comprehensive, production-grade backend service designed to intelligently score and validate user-generated content for a decentralized application. It uses a sophisticated, multi-stage AI pipeline to ensure content quality and originality, and a robust, asynchronous architecture to handle requests at scale.

## Table of Contents

1.  [Core Concepts & Architecture](#core-concepts--architecture)
2.  [Project Structure](#project-structure)
3.  [File-by-File Explanation](#file-by-file-explanation)
4.  [Technology Stack](#technology-stack)
5.  [The Scoring System Explained](#the-scoring-system-explained)
6.  [API Endpoints](#api-endpoints)
7.  [How to Run the Project](#how-to-run-the-project)
    *   [Prerequisites](#prerequisites)
    *   [Local Development Setup](#local-development-setup)
    *   [Production Setup with Docker Compose](#production-setup-with-docker-compose)
8.  [How to Test the System](#how-to-test-the-system)
9.  [Workflow Diagram Prompt](#workflow-diagram-prompt)
10. [Future To-Do's & Improvements](#future-to-dos--improvements)

## Core Concepts & Architecture

The entire system is built on a **Service-Oriented Architecture (SOA)** and designed to be **asynchronous** to handle slow AI processing without degrading user experience.

The core workflow is as follows:
1.  **Request Ingestion:** A client (e.g., the blockchain team's main application) sends a user "interaction" (like a post, like, or comment) to our **FastAPI** server.
2.  **Interaction Routing:** The API server intelligently routes the request to one of two specialized endpoints.
    *   **Fast, Synchronous Actions** (`/v1/submit_action`): For simple interactions like 'like' or 'comment', the API processes the request immediately. The `ScoringEngine` updates the user's score in the **PostgreSQL** database, and a final JSON response is sent back instantly.
    *   **Slow, Asynchronous Actions** (`/v1/submit_post`): For complex interactions like a new post that requires AI analysis, the API places a "job" onto a **Redis** queue and immediately responds to the client with a `202 Accepted` status.
3.  **Background AI Processing:** A separate **Celery Worker** process is constantly listening to the Redis queue. It picks up the job and begins the heavy lifting:
    *   **Validation:** The `ContentValidator` checks the post for gibberish and uses a **Weaviate** vector database to check for plagiarism/duplicates.
    *   **Qualitative Scoring:** If the post is valid, the `OllamaQualityScorer` sends the content to a local **LLM (`qwen2.5vl`)** to get a quality rating.
    *   **Database Update:** The `ScoringEngine` calculates the final `significanceScore` and updates the user's record in the **PostgreSQL** database.
4.  **Webhook Callback:** Once the background job is complete (whether it succeeded or failed), the Celery worker sends the final, detailed `AIResponse` JSON to a `webhookUrl` that was provided in the initial request. This informs the client application of the outcome.

This architecture ensures the system is **scalable** (you can add more Celery workers to handle more load), **resilient** (the Redis queue ensures jobs aren't lost if a worker restarts), and **performant** (the user gets an instant response for slow tasks).

## File-by-File Explanation

-   **`api/main.py`**: This is the front door to the application. It uses the FastAPI framework to define two main endpoints: `/v1/submit_action` for fast, synchronous tasks and `/v1/submit_post` for slow, asynchronous tasks. It is responsible for receiving HTTP requests, validating the input using Pydantic models, and either processing the request directly or delegating it to the Celery worker.

-   **`celery_worker.py`**: This file defines the background worker. It configures Celery to use Redis as a message broker. The single task, `process_and_score_post_task`, contains the full pipeline for handling a new post: it calls the validator, then the scorer, and finally sends the result to a webhook. Instantiating services *inside* the task ensures process safety.

-   **`core/ai_validator.py`**: This module contains the `ContentValidator` class, which acts as the first line of defense for content quality.
    -   It connects to the **Weaviate** vector database.
    -   It performs a multi-layered gibberish check (rule-based, statistical, and ML-based).
    -   Its most critical function is `check_for_duplicates`, which uses Weaviate's `near_text` search to find and reject plagiarized or very similar content.

-   **`core/ollama_scorer.py`**: This module's `OllamaQualityScorer` class is responsible for the qualitative AI analysis.
    -   It connects to a locally running **Ollama** server.
    -   Its `get_quality_score` method sends the post's text (and optionally an image) to the `qwen2.5vl` model with a carefully engineered prompt.
    -   It includes robust error handling and a retry mechanism to deal with slow LLM responses.

-   **`core/scoring_engine.py`**: The `ScoringEngine` is the system's accountant.
    -   It connects to the **PostgreSQL** database and manages the `user_scores` table.
    -   It contains methods for every scoring action (`add_like_points`, `add_qualitative_post_points`, etc.). Each method performs a direct, atomic transaction with the database to ensure data integrity.
    -   It calculates the final normalized 0-100 score.

-   **`core/scoring_config.py`**: A centralized configuration file. All magic numbers (point values, monthly caps, etc.) are stored here. Changing a scoring rule is as simple as changing a value in this file.

-   **`docker-compose.yml`**: The production deployment manifest. It defines all the services needed to run the application (Postgres, Redis, Weaviate, the API, the Worker) and how they connect to each other.

-   **`Dockerfile`**: A standard recipe to build a production-ready, portable container image of the Python application, ensuring all dependencies are included.

## Technology Stack

-   **Application Framework:** **FastAPI** for its high performance and automatic OpenAPI documentation.
-   **Asynchronous Task Queue:** **Celery** with a **Redis** broker for offloading slow AI tasks and ensuring a responsive API.
-   **Vector Database:** **Weaviate** for storing content embeddings and performing high-speed semantic similarity searches for duplicate/plagiarism detection.
-   **Relational Database:** **PostgreSQL** for persistent, transactional storage of all user scores.
-   **Local LLM Server:** **Ollama** for serving the `qwen2.5vl` multimodal model locally, enabling powerful qualitative content analysis without relying on external APIs.
-   **Containerization:** **Docker** and **Docker Compose** for creating a reproducible and easily deployable production environment.

## The Scoring System Explained

The scoring system is designed to be fair, transparent, and resistant to "gaming". It consists of two parts:

### 1. The 0-100 Normalized Monthly Score

This score reflects a user's engagement over a single month. It is calculated as a percentage of the total possible points earnable in that month.

-   **`TOTAL_POSSIBLE_MONTHLY_POINTS`**: This is the "perfect score" for a month, defined in `scoring_config.py`. It is currently **90**.
    -   Posts: 30 points max
    -   Likes: 15 points max
    -   Comments: 15 points max
    -   Referrals: 10 points max
    -   Tipping: 20 points max
-   **Calculation:** `Final Score = (User's Raw Monthly Points / 90) * 100`

### 2. Qualitative Post Scoring

Instead of a fixed value, each post's score (`significanceScore`) is calculated dynamically:

-   **Originality Score (40% weight):** Based on the vector distance to the most similar existing post in Weaviate. A more unique post gets more points.
-   **Quality Score (60% weight):** Based on a 0-10 rating from the Ollama LLM, which analyzes the post's effort, creativity, and clarity.
-   **Max Points:** A perfect post (max originality, 10/10 quality) earns **2.5 points**.

## API Endpoints

The service exposes two primary endpoints:

### `POST /v1/submit_action`

-   **Purpose:** For simple, fast, synchronous interactions.
-   **Content-Type:** `application/json`
-   **Request Body:** A raw `BlockchainRequestModel` JSON object.
-   **Response:** An immediate `200 OK` with the final `AIResponse` JSON containing the points awarded and the user's new total score.

### `POST /v1/submit_post`

-   **Purpose:** For complex, slow, asynchronous post submissions that may include an image.
-   **Content-Type:** `multipart/form-data`
-   **Request Body:**
    -   A form field named `request` containing the `BlockchainRequestModel` as a JSON string.
    -   An optional form field named `image` containing the image file.
-   **Response:**
    -   An immediate `202 Accepted` to confirm the job was queued.
    -   The final `AIResponse` JSON is sent later to the `webhookUrl` provided in the request.

## How to Run the Project

### Prerequisites

-   Docker & Docker Compose
-   Python 3.11+
-   Ollama installed and running (`ollama run qwen2.5vl`)

### Local Development Setup

This setup is for testing the Python code directly without full containerization.

1.  **Start Infrastructure:**
    ```bash
    docker-compose up -d postgres redis weaviate multi2vec-clip
    ```
2.  **Start Celery Worker:**
    ```bash
    celery -A celery_worker.celery_app worker --loglevel=info
    ```
3.  **Start API Server:**
    ```bash
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
    ```

### Production Setup with Docker Compose

This is the recommended method. It builds and runs the entire application stack with a single command. **Before running, you must update the code to use Docker service names instead of `localhost` for inter-container communication.**

1.  **Build and Run:**
    ```bash
    docker-compose up --build
    ```

## How to Test the System

Use the `run_all_tests.py` script for a comprehensive test of all features.

1.  **Get a Webhook URL:** Go to https://webhook.site and copy your new unique URL.
2.  **Update the Script:** Paste the URL into the `WEBHOOK_URL` variable in `run_all_tests.py`.
3.  **Run the Test:**
    ```bash
    python run_all_tests.py
    ```
## Flow Diagram
![alt text](utils/image.png)
**Expected Test Outcomes:**
-   **Like/Comment Tests:** You will see immediate `200 OK` responses in your terminal with the calculated scores.
-   **High-Quality Post Test:** You will get a `202 Accepted` response. The webhook will receive a success JSON with a high `significanceScore` (e.g., > 2.0).
-   **Text-Only Post Test:** You will get a `202 Accepted` response. The webhook will receive a success JSON with a moderate `significanceScore` (e.g., ~1.0).
-   **Duplicate Post Test:** You will get a `202 Accepted` response. The webhook will receive a **failure** JSON with `aiAgentResponseApproved: false`.

## Future To-Do's & Improvements

-   [ ] **Configuration Management:** Move all secrets (database passwords, etc.) and connection strings (`localhost`) into environment variables for production security and flexibility.
-   [ ] **Webhook Retries:** Implement a retry mechanism in the Celery worker (e.g., `self.retry(exc=e)`) for when a webhook call fails, to ensure results are not lost.
-   [ ] **Structured Logging:** Replace all `print()` statements with Python's `logging` module to allow for log-level filtering and redirection to file or cloud logging services.
-   [ ] **Scalability Testing:** Use a load testing tool like `locust.io` to benchmark the API and determine how many Celery workers are needed to handle the expected load.
-   [ ] **Monthly Score Reset:** Implement a scheduled job (e.g., a Celery Beat task or a cron job) that runs on the first of every month to reset the monthly point columns (`points_from_posts`, etc.) in the PostgreSQL database.
