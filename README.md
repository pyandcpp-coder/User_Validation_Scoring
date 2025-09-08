# Intelligent Scoring System

A comprehensive AI-powered scoring and reward system for social platform interactions, featuring content validation, quality assessment, and category-based reward distribution.

## Table of Contents
- [System Overview](#system-overview)
- [Architecture](#architecture)
- [Core Components](#core-components)
- [Scoring Logic](#scoring-logic)
- [Reward System](#reward-system)
- [Database Design](#database-design)
- [API Documentation](#api-documentation)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [Daily Operations](#daily-operations)
- [Troubleshooting](#troubleshooting)

## System Overview

This system validates user-generated content, assigns quality scores, tracks user engagement, and distributes rewards based on activity patterns. It prevents spam/gibberish, detects duplicates, and rewards both active users and loyal but less active users through an "empathy" mechanism.

### Key Features
- **Content Validation**: Gibberish detection, duplicate checking
- **Quality Scoring**: AI-powered content quality assessment using Ollama
- **Multi-Category Rewards**: Posts, likes, comments, crypto, tipping, referrals
- **Daily & Monthly Limits**: Prevents gaming the system
- **Empathy Rewards**: Top 10% of non-qualified users still get rewards
- **Asynchronous Processing**: Celery workers for scalable content processing
- **Post Management**: Custom post IDs with delete functionality

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                         │
│                    (Web/Mobile Applications)                │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                      API GATEWAY                            │
│                    FastAPI (main.py)                        │
│                     Port: 8000                              │
└──────┬──────────────────────────────────────────┬───────────┘
       │                                          │
       │ Synchronous                              │ Asynchronous
       │ (likes, tips, referrals)                │ (posts, comments)
       │                                          │
┌──────▼──────────┐                    ┌─────────▼────────────┐
│  Scoring Engine │                    │   Celery Workers     │
│  (PostgreSQL)   │                    │   - Post validation  │
│                 │◄───────────────────│   - Comment check    │
└─────────────────┘                    │   - Quality scoring  │
                                       └──────────┬───────────┘
                                                  │
┌─────────────────────────────────────────────────▼───────────┐
│                        DATA LAYER                           │
├──────────────┬──────────────┬──────────────┬───────────────┤
│  PostgreSQL  │   Weaviate   │    Redis     │    Ollama     │
│   (Scores)   │   (Posts)    │   (Queue)    │  (AI Scoring) │
└──────────────┴──────────────┴──────────────┴───────────────┘
```

### Data Flow
1. **User Action** → API Gateway
2. **Synchronous Actions** (likes, tips) → Direct scoring
3. **Asynchronous Actions** (posts, comments) → Celery queue → Validation → Scoring
4. **Storage**: Posts in Weaviate, Scores in PostgreSQL
5. **Daily Analysis** → Reward distribution

## Core Components

### 1. API Service (main.py)
- **Framework**: FastAPI
- **Purpose**: REST API gateway for all interactions
- **Key Endpoints**:
  - `/v1/submit_post`: Handles posts with images
  - `/v1/submit_action`: Handles likes, comments, tips, etc.
  - `/v1/delete/{post_id}`: Deletes posts
  - `/admin/*`: Administrative functions
  - `/api/rewards/*`: Reward distribution endpoints

### 2. Content Validator (ai_validator.py)
- **Gibberish Detection**: 
  - Rule-based checks (keyboard patterns, vowel ratios)
  - Statistical analysis (word lengths, character frequencies)
  - ML model (BERT-based classifier)
- **Duplicate Detection**: Vector similarity using CLIP embeddings
- **Storage**: Weaviate vector database
- **Post Management**: Store with custom post_id, delete by post_id

### 3. Scoring Engine (scoring_engine.py)
- **Points System**: Different points for different actions
- **Daily Limits**: Prevents spam (e.g., max 2 posts/day)
- **Monthly Caps**: Maximum points per category
- **Quality Bonuses**: Extra points for high-quality content
- **Database Pool**: Connection pooling for performance

### 4. Ollama Quality Scorer (ollama_scorer.py)
- **Model**: qwen2.5vl (multimodal)
- **Scoring**: 0-10 quality score for posts
- **Factors**: Effort, creativity, clarity
- **Retry Logic**: Handles API failures gracefully

### 5. Historical Analyzer (historical_analyzer.py)
- **Daily Analysis**: Runs every 24 hours
- **Category-wise Qualification**: Each category has independent requirements
- **Empathy System**: Rewards top 10% of non-qualified users
- **Streak Tracking**: Consecutive activity days

### 6. Celery Workers (celery_worker.py)
- **Async Processing**: Posts and comments
- **Scheduled Tasks**: Daily reward analysis
- **Webhook Callbacks**: Notifies external systems
- **Beat Scheduler**: Automated daily tasks

## Scoring Logic

### Action Points
```python
POINTS_PER_POST = 0.5 (+ quality bonus up to 1.0 + originality bonus up to 0.25)
POINTS_PER_LIKE = 0.1
POINTS_PER_COMMENT = 0.1
POINTS_PER_REFERRAL = 10
POINTS_FOR_TIPPING = 0.5
POINTS_FOR_CRYPTO = 0.5
```

### Daily Requirements for Qualification
```python
POST_LIMIT_DAY = 2      # Must make 2 posts to qualify
LIKE_LIMIT_DAY = 5      # Must make 5 likes to qualify
COMMENT_LIMIT_DAY = 5   # Must make 5 comments to qualify
CRYPTO_LIMIT_DAY = 3    # Must make 3 crypto transactions to qualify
TIPPING_LIMIT_DAY = 1   # Must tip once to qualify
REFERRAL_LIMIT_DAY = 1  # Must refer once to qualify
```

### Monthly Maximum Points
```python
MAX_MONTHLY_POST_POINTS = 30
MAX_MONTHLY_LIKE_POINTS = 15
MAX_MONTHLY_COMMENT_POINTS = 15
MAX_MONTHLY_REFERRAL_POINTS = 10
MAX_MONTHLY_TIPPING_POINTS = 20
MAX_MONTHLY_CRYPTO_POINTS = 20
TOTAL_POSSIBLE_MONTHLY_POINTS = 110
```

### Quality Score Calculation (Posts)
```
Total Points = Base Points + Quality Bonus + Originality Bonus
- Base: 0.5 points
- Quality Bonus: (AI Score / 10) * 1.0 (max 1.0)
- Originality Bonus: Distance * 0.25 (max 0.25)
Maximum per post: 1.75 points
```

### Final Score Calculation
```python
Final Score = (Total Monthly Points / Total Possible Points) * 100
Range: 0-100
```

## Reward System

### Category-Based Rewards
Each category operates independently:
1. **Qualified Users**: Meet daily requirements, get full rewards
2. **Empathy Users**: Top 10% of non-qualified but historically active users

### Empathy Score Calculation
```python
Empathy Score = Streak Component + Category Activity Component
- Streak: consecutive_days * 0.5
- Activity: lifetime_actions * category_weight

Weights:
- Posts: 0.25
- Likes: 0.08
- Comments: 0.08
- Crypto: 0.09
- Tipping: 0.05
- Referrals: 0.05
```

### Daily Reward Process
1. Analyze all users' 24-hour activity
2. Determine qualification per category
3. Calculate empathy scores for non-qualified
4. Select top 10% for empathy rewards
5. Update streaks and engagement scores
6. Distribute rewards via API

## Database Design

### PostgreSQL (user_scores table)
```sql
CREATE TABLE user_scores (
    user_id VARCHAR(255) PRIMARY KEY,
    points_from_posts REAL DEFAULT 0.0,
    points_from_likes REAL DEFAULT 0.0,
    points_from_comments REAL DEFAULT 0.0,
    points_from_referrals REAL DEFAULT 0.0,
    points_from_tipping REAL DEFAULT 0.0,
    points_from_crypto REAL DEFAULT 0.0,
    one_time_points REAL DEFAULT 0.0,
    one_time_events TEXT[] DEFAULT ARRAY[]::TEXT[],
    last_reset_date DATE NOT NULL DEFAULT CURRENT_DATE,
    daily_posts_timestamps TIMESTAMPTZ[],
    daily_likes_timestamps TIMESTAMPTZ[],
    daily_comments_timestamps TIMESTAMPTZ[],
    daily_referrals_timestamps TIMESTAMPTZ[],
    daily_tipping_timestamps TIMESTAMPTZ[],
    daily_crypto_timestamps TIMESTAMPTZ[],
    last_active_date DATE,
    consecutive_activity_days INTEGER DEFAULT 0,
    historical_engagement_score REAL DEFAULT 0.0
);
```

### Weaviate (Post collection)
```json
{
    "post_id": "unique-identifier",
    "content": "post text content",
    "user_id": "user wallet address",
    "image": "base64 encoded image"
}
```

### Redis
- **Purpose**: Message queue for Celery
- **Queues**: Default queue for async tasks
- **Result Backend**: Stores task results

## API Documentation

### Content Submission

#### Submit Post (Multipart Form)
```http
POST /v1/submit_post
Content-Type: multipart/form-data

Fields:
- creatorAddress: string (required)
- interactorAddress: string (required)
- data: string (required) - post content
- webhookUrl: string (required)
- post_id: string (required) - unique identifier
- image: file (optional)

Response: 202 Accepted
{
    "status": "processing",
    "message": "Post accepted for validation and scoring."
}
```

#### Submit Action (JSON)
```http
POST /v1/submit_action
Content-Type: application/json

{
    "creatorAddress": "0x123...",
    "interactorAddress": "0x456...",
    "Interaction": {
        "interactionType": "like|comment|tipping|crypto|referral",
        "data": "optional data"
    },
    "webhookUrl": "https://callback.url" (optional)
}

Response: 200 OK (for synchronous) or 202 Accepted (for async)
{
    "creatorAddress": "0x123...",
    "interactorAddress": "0x456...",
    "validation": {
        "aiAgentResponseApproved": true,
        "significanceScore": 0.1234,
        "reason": "Interaction processed successfully.",
        "finalUserScore": 45.67
    }
}
```

#### Delete Post
```http
DELETE /v1/delete/{post_id}?user_id={user_id}

Response: 200 OK
{
    "status": "success",
    "message": "Post deleted successfully",
    "post_id": "post-123",
    "user_id": "0x456..."
}

Response: 404 Not Found
{
    "status": "error",
    "message": "Post not found or doesn't belong to user"
}
```

### Admin Endpoints

#### Run Daily Analysis
```http
POST /admin/run-daily-analysis

Response: 200 OK
{
    "status": "success",
    "message": "Category-wise daily analysis completed",
    "analysis_type": "category_based",
    "results": {...}
}
```

#### Get Daily Summary
```http
GET /admin/daily-summary

Response: 200 OK
{
    "status": "success",
    "data": {
        "categories": {...},
        "overall_summary": {...}
    }
}
```

#### Get User Activity
```http
GET /admin/user-activity/{user_id}

Response: 200 OK
{
    "status": "success",
    "user_id": "0x123...",
    "category_breakdown": {...},
    "engagement_data": {...},
    "reward_eligibility": {...}
}
```

#### Get Category Rewards
```http
GET /api/rewards/{category}
Categories: posts, likes, comments, crypto, tipping, referrals, all

Response: 200 OK
{
    "status": "success",
    "category": "posts",
    "daily_requirement": 2,
    "qualified_users": [...],
    "empathy_users": [...],
    "stats": {...}
}
```

## Installation & Setup

### Prerequisites
- Docker & Docker Compose
- Python 3.9+
- 8GB+ RAM recommended
- Disk space: 20GB+ for models and data

### Environment Variables (.env)
```env
# Database
POSTGRES_DB=scoring_db
POSTGRES_USER=scoring_user
POSTGRES_PASSWORD=scoring_password
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Redis
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Weaviate
WEAVIATE_HOST=weaviate
WEAVIATE_PORT=8080
WEAVIATE_GRPC_PORT=50051

# Ollama
OLLAMA_HOST_URL=http://ollama:11434
```

### Quick Start
```bash
# 1. Clone repository
git clone <repository-url>
cd intelligent-scoring-system

# 2. Create .env file
cp .env.example .env
# Edit .env with your configuration

# 3. Start services
docker-compose up -d

# 4. Install Ollama model (if using local Ollama)
docker exec -it ollama ollama pull qwen2.5vl

# 5. Initialize database (automatic on first run)
# The system will create tables automatically

# 6. Verify health
curl http://localhost:8000/health
curl http://localhost:8000/health/weaviate

# 7. Start Celery beat (for scheduled tasks)
docker-compose exec worker celery -A celery_worker beat --loglevel=info
```

### Docker Compose Services
```yaml
services:
  postgres:     # Database for scores
  redis:        # Message queue
  weaviate:     # Vector database
  multi2vec-clip: # CLIP model for embeddings
  api:          # FastAPI application
  worker:       # Celery worker
  beat:         # Celery beat scheduler
```

### Service Ports
- API: `http://localhost:8000`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- Weaviate: `http://localhost:8080`
- Weaviate gRPC: `localhost:50051`
- Ollama: `http://localhost:11434`

## Configuration

### Adjusting Scoring Parameters
Edit `scoring_config.py`:
```python
# Modify points per action
POINTS_PER_POST = 0.5  # Change base points

# Adjust daily limits
POST_LIMIT_DAY = 2  # Change daily requirement

# Change monthly caps
MAX_MONTHLY_POST_POINTS = 30  # Modify monthly maximum

# Empathy reward percentage
REWARD_PERCENTAGE_OF_INACTIVE = 0.10  # Top 10%
```

### Celery Beat Schedule
Edit `celery_worker.py`:
```python
celery_app.conf.beat_schedule = {
    'run-daily-user-analysis': {
        'task': 'daily_empathy_analysis_task',
        'schedule': 86400.0,  # 24 hours (change for testing)
    }
}
```

### Gibberish Detection Sensitivity
Edit `ai_validator.py`:
```python
# Rule-based thresholds
if consonant_ratio > 0.85:  # Adjust ratio

# ML model confidence
if result['score'] > 0.85:  # Adjust threshold
```

### Duplicate Detection Threshold
Edit `ai_validator.py`:
```python
threshold: float = 0.1  # Lower = stricter
```

## Daily Operations

### Automated Daily Reward Distribution

#### Using Cron
```bash
# Edit crontab
crontab -e

# Add daily execution at 1 AM UTC
0 1 * * * /path/to/daily_reward_script.sh
```

#### Using Docker
```bash
# Celery beat handles scheduling automatically
docker-compose up -d beat
```

### Manual Operations

#### Check System Health
```bash
# API health
curl http://localhost:8000/health

# Weaviate health
curl http://localhost:8000/health/weaviate

# Database connection
curl http://localhost:8000/debug/db
```

#### Trigger Manual Analysis
```bash
curl -X POST http://localhost:8000/admin/run-daily-analysis
```

#### View User Score
```bash
curl http://localhost:8000/admin/user-activity/USER_ID
```

#### Get Category Summary
```bash
curl http://localhost:8000/admin/category-summary
```

### Monitoring

#### View Logs
```bash
# API logs
docker-compose logs api -f

# Worker logs
docker-compose logs worker -f

# Beat scheduler logs
docker-compose logs beat -f
```

#### Database Queries
```sql
-- Top scorers
SELECT user_id, 
       points_from_posts + points_from_likes + points_from_comments + 
       points_from_referrals + points_from_tipping + points_from_crypto as total
FROM user_scores 
ORDER BY total DESC 
LIMIT 10;

-- Active users today
SELECT COUNT(DISTINCT user_id) 
FROM user_scores 
WHERE last_active_date = CURRENT_DATE;

-- Users by streak
SELECT user_id, consecutive_activity_days 
FROM user_scores 
WHERE consecutive_activity_days > 0 
ORDER BY consecutive_activity_days DESC;

-- Category-wise activity
SELECT 
    COUNT(CASE WHEN cardinality(daily_posts_timestamps) > 0 THEN 1 END) as post_users,
    COUNT(CASE WHEN cardinality(daily_likes_timestamps) > 0 THEN 1 END) as like_users
FROM user_scores
WHERE last_active_date = CURRENT_DATE;
```

#### Redis Monitoring
```bash
# Check queue length
docker-compose exec redis redis-cli LLEN celery

# Monitor in real-time
docker-compose exec redis redis-cli MONITOR
```

## Troubleshooting

### Common Issues

#### 1. Weaviate Connection Failed
```bash
# Check if Weaviate is running
docker-compose ps weaviate

# Check logs
docker-compose logs weaviate

# Verify CLIP module
curl http://localhost:8080/v1/meta
```

#### 2. Ollama Timeout
```bash
# Check if model is downloaded
docker exec -it ollama ollama list

# Pull model if missing
docker exec -it ollama ollama pull qwen2.5vl

# Increase timeout in ollama_scorer.py
timeout=120  # Increase to 240
```

#### 3. Celery Tasks Not Running
```bash
# Check Redis connection
docker-compose exec redis redis-cli ping

# Verify worker is processing
docker-compose logs worker | grep "ready"

# Check beat scheduler
docker-compose logs beat | grep "beat: Starting"
```

#### 4. Database Pool Exhausted
```python
# In scoring_engine.py, increase pool size
self.db_pool = SimpleConnectionPool(
    minconn=1, 
    maxconn=20,  # Increase from 10
    ...
)
```

#### 5. Posts Not Being Validated
```bash
# Check webhook is being called
docker-compose logs worker | grep "webhook"

# Verify Weaviate has space
curl http://localhost:8080/v1/nodes
```

### Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `FATAL: ScoringEngine could not connect` | PostgreSQL down | Check postgres container |
| `Post rejected: Content is gibberish` | Failed validation | Adjust thresholds |
| `User has reached daily limit` | Too many actions | Wait 24 hours |
| `DUPLICATE DETECTED` | Similar content exists | Create unique content |
| `All retry attempts failed` | Ollama unavailable | Restart Ollama service |

## Performance Optimization

### Database Indexes
```sql
-- Add indexes for frequent queries
CREATE INDEX idx_last_active ON user_scores(last_active_date);
CREATE INDEX idx_user_streak ON user_scores(consecutive_activity_days);
```

### Caching Strategy
- Redis for frequently accessed scores
- In-memory caching for configuration
- Connection pooling for databases

### Scaling Options
- Horizontal scaling: Add more Celery workers
- Vertical scaling: Increase container resources
- Load balancing: Multiple API instances

## Security Considerations

### Current Implementation
- Wallet addresses as user IDs (pseudonymous)
- Post IDs must be globally unique
- Webhook URLs for async callbacks
- No built-in authentication

### Recommended Additions
```python
# Add API key authentication
from fastapi.security import APIKeyHeader

# Add rate limiting
from slowapi import Limiter

# Add input validation
from pydantic import validator

# Add HTTPS enforcement
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
```

## Development

### Project Structure
```
intelligent-scoring-system/
├── api/
│   └── main.py              # FastAPI application
├── core/
│   ├── ai_validator.py      # Content validation
│   ├── scoring_engine.py    # Points calculation
│   ├── scoring_config.py    # Configuration
│   ├── ollama_scorer.py     # AI quality scoring
│   └── historical_analyzer.py # Daily analysis
├── celery_worker.py         # Async task processing
├── docker-compose.yml       # Service orchestration
├── Dockerfile              # Container definition
├── requirements.txt        # Python dependencies
├── .env                   # Environment variables
└── daily_reward_script.sh # Cron job script
```

### Testing
```bash
# Test post submission
curl -X POST http://localhost:8000/v1/submit_post \
  -F "creatorAddress=0x123" \
  -F "interactorAddress=0x123" \
  -F "data=Test post content" \
  -F "webhookUrl=https://webhook.site/your-url" \
  -F "post_id=test-001"

# Test like action
curl -X POST http://localhost:8000/v1/submit_action \
  -H "Content-Type: application/json" \
  -d '{
    "creatorAddress": "0x123",
    "interactorAddress": "0x456",
    "Interaction": {
      "interactionType": "like"
    }
  }'
```
