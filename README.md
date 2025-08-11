# Intelligent Category-wise Scoring & Validation Service

A production-grade backend service that intelligently scores and validates user-generated content using AI, with **category-wise qualification system** for flexible user rewards.

## 🎯 Core Features

### **Category-wise Qualification System**
Instead of requiring users to complete ALL daily activities, users can now qualify for rewards in **individual categories**:

- **📝 Posts:** Create 2 quality posts → qualify for post rewards
- **👍 Likes:** Give 5 likes → qualify for like rewards  
- **💬 Comments:** Make 5 comments → qualify for comment rewards
- **🪙 Crypto:** Complete 3 crypto transactions → qualify for crypto rewards
- **💰 Tipping:** Make 1 tip → qualify for tipping rewards
- **🤝 Referrals:** Refer 1 person → qualify for referral rewards

### **Empathy Reward System**
- Users who don't qualify in a category can still receive **empathy rewards**
- Top 10% of non-qualified users per category get empathy rewards based on historical engagement
- Fair distribution ensures loyal users are recognized

### **AI-Powered Content Validation**
- **Gibberish Detection:** Multi-layered approach (rule-based, statistical, ML)
- **Duplicate Detection:** Vector-based similarity using Weaviate database
- **Quality Scoring:** Local LLM (qwen2.5vl) rates content quality 0-10
- **Originality Bonus:** More unique content gets higher points

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Client App    │───▶│   FastAPI Server │───▶│  Celery Worker  │
│  (Blockchain)   │    │                  │    │   (AI Engine)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │   PostgreSQL    │    │    Weaviate     │
                       │  (User Scores)  │    │  (Embeddings)   │
                       └─────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │     Redis       │    │     Ollama      │
                       │ (Task Queue)    │    │  (Local LLM)    │
                       └─────────────────┘    └─────────────────┘
```

## 📊 Scoring System

### **Monthly Point Distribution (Total: 110 points)**
| Category | Max Points | Percentage | Daily Requirement |
|----------|------------|------------|-------------------|
| Posts | 30 | 27.3% | 2 posts/day |
| Crypto | 20 | 18.2% | 3 transactions/day |
| Tipping | 20 | 18.2% | 1 tip/day |
| Likes | 15 | 13.6% | 5 likes/day |
| Comments | 15 | 13.6% | 5 comments/day |
| Referrals | 10 | 9.1% | 1 referral/day |

### **Final Score Calculation**
```
Final Score = (User's Total Points / 110) × 100
```

### **Post Quality Scoring**
```
Post Points = Base (0.5) + Quality Bonus (0-1.0) + Originality Bonus (0-0.25)
```

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Ollama with qwen2.5vl model

### Installation

1. **Clone and Setup**
   ```bash
   git clone <repository>
   cd User_Validation_Scoring
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Start Infrastructure**
   ```bash
   docker-compose up -d postgres redis weaviate multi2vec-clip
   ```

3. **Install Ollama Model**
   ```bash
   ollama pull qwen2.5vl
   ollama run qwen2.5vl  # Keep running in separate terminal
   ```

4. **Start Services**
   ```bash
   # Terminal 1: Start Celery Worker
   celery -A celery_worker worker --loglevel=info
   
   # Terminal 2: Start API Server
   uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
   
   # Terminal 3: Start Scheduler (Optional)
   celery -A celery_worker beat --loglevel=info
   ```

5. **Verify Setup**
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/admin/category-summary
   ```

## 📚 API Endpoints

### **Core Endpoints**

#### Submit Simple Action (Synchronous)
```http
POST /v1/submit_action
Content-Type: application/json

{
  "creatorAddress": "0x...",
  "interactorAddress": "0x...",
  "Interaction": {
    "interactionType": "like|crypto|tipping|referral",
    "data": "optional_data"
  }
}
```

#### Submit Post (Asynchronous)
```http
POST /v1/submit_post
Content-Type: multipart/form-data

creatorAddress: 0x...
interactorAddress: 0x...
interactionType: post
data: "Post content here"
webhookUrl: https://your-webhook.com/callback
image: [optional file upload]
```

### **Admin Endpoints**

#### Get Category Summary
```http
GET /admin/category-summary
```

#### Get Daily Analysis Summary
```http
GET /admin/daily-summary
```

#### Get User Activity
```http
GET /admin/user-activity/{wallet_address}
```

#### Run Daily Analysis
```http
POST /admin/run-daily-analysis
```

## 🧪 Testing

### **Quick Test**
```bash
# Test crypto interaction
curl -X POST http://localhost:8000/v1/submit_action \
  -H "Content-Type: application/json" \
  -d '{
    "creatorAddress": "0x1234567890abcdef1234567890abcdef12345678",
    "interactorAddress": "0x1234567890abcdef1234567890abcdef12345678",
    "Interaction": {
      "interactionType": "crypto",
      "data": "BTC_TRADE_12345"
    }
  }'
```

### **Comprehensive Test**
```bash
python testing/category_test_script.py
```

## 📈 Daily Analysis Process

### **How Category-wise Analysis Works**

1. **Individual Category Check:** For each category (posts, likes, comments, crypto, tipping, referrals):
   - Check which users met the daily requirement
   - Mark them as "qualified" for that specific category

2. **Empathy Selection:** For each category:
   - Calculate empathy scores for non-qualified users
   - Select top 10% as empathy recipients

3. **Reward Distribution:** 
   - Send category-wise API calls with qualified and empathy user lists
   - Users can qualify for multiple categories simultaneously

### **Example Daily Results**
```json
{
  "posts": {
    "qualified": ["0x1111...", "0x4444..."],
    "empathy": ["0x5555..."]
  },
  "likes": {
    "qualified": ["0x2222...", "0x4444..."],
    "empathy": ["0x1111..."]
  },
  "crypto": {
    "qualified": ["0x3333...", "0x4444..."],
    "empathy": []
  }
}
```

## 🔧 Configuration

### **Key Settings** (`core/scoring_config.py`)
```python
# Daily qualification requirements
POST_LIMIT_DAY = 2
LIKE_LIMIT_DAY = 5
COMMENT_LIMIT_DAY = 5
CRYPTO_LIMIT_DAY = 3
TIPPING_LIMIT_DAY = 1
REFERRAL_LIMIT_DAY = 1

# Point values
POINTS_PER_POST = 0.5
POINTS_FOR_CRYPTO = 0.5
POINTS_FOR_TIPPING = 0.5
# ... etc

# Empathy reward percentage
REWARD_PERCENTAGE_OF_INACTIVE = 0.10  # Top 10%
```

## 🗃️ Database Schema

### **User Scores Table**
```sql
CREATE TABLE user_scores (
    user_id VARCHAR(255) PRIMARY KEY,
    points_from_posts REAL DEFAULT 0.0,
    points_from_likes REAL DEFAULT 0.0,
    points_from_comments REAL DEFAULT 0.0,
    points_from_referrals REAL DEFAULT 0.0,
    points_from_tipping REAL DEFAULT 0.0,
    points_from_crypto REAL DEFAULT 0.0,
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

## 🛠️ Maintenance

### **Database Cleanup**
```bash
python clean.py  # Resets all data
```

### **View Logs**
```bash
# API logs
tail -f api_logs.log

# Celery worker logs
celery -A celery_worker worker --loglevel=debug

# Docker logs
docker-compose logs -f api worker
```

## 🎯 Benefits of Category-wise System

### **Before (All-or-Nothing)**
- Users needed to complete ALL daily activities to qualify
- Lower participation rate
- Users forced into activities they didn't prefer

### **After (Category-wise)**
- Users qualify independently for each category they're active in
- Higher participation and engagement
- Users can focus on preferred activities
- More flexible and user-friendly
- Better retention and satisfaction

## 🔮 Production Deployment

### **Docker Compose (Full Stack)**
```bash
# Update connection strings in code to use service names
# postgres -> postgres:5432
# redis -> redis:6379
# weaviate -> weaviate:8080

docker-compose up --build
```

### **Environment Variables**
```env
POSTGRES_HOST=postgres
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
WEAVIATE_HOST=weaviate
OLLAMA_HOST_URL=http://host.docker.internal:11434
```

## 📞 Support

- **API Documentation:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health
- **Category Status:** http://localhost:8000/admin/category-summary

---

## 🎊 Key Achievement: Category-wise Independence

This system revolutionizes user engagement by allowing **independent qualification per category**, making it much more user-friendly and increasing overall participation while maintaining quality standards through AI validation.