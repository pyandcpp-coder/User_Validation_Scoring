# Points awarded per action
POINTS_PER_POST = 0.5
POINTS_PER_LIKE = 0.1
POINTS_PER_COMMENT = 0.1
POINTS_PER_REFERRAL = 10  
POINTS_FOR_TIPPING = 0.5  
POINTS_FOR_CRYPTO = 0.5

# One-time registration/verification points
POINTS_FOR_REGISTRATION = 10
POINTS_FOR_VERIFICATION = 10

# CATEGORY-WISE DAILY LIMITS FOR QUALIFICATION
# Users need to meet these daily requirements to qualify in each category
POST_LIMIT_DAY = 2          # Need 2 posts per day to qualify for "post rewards"
LIKE_LIMIT_DAY = 5          # Need 5 likes per day to qualify for "like rewards"  
COMMENT_LIMIT_DAY = 5       # Need 5 comments per day to qualify for "comment rewards"
CRYPTO_LIMIT_DAY = 3        # Need 3 crypto interactions per day to qualify for "crypto rewards"
TIPPING_LIMIT_DAY = 1       # Need 1 tipping action per day to qualify for "tipping rewards"
REFERRAL_LIMIT_DAY = 1      # Need 1 referral per day to qualify for "referral rewards"

# Monthly maximum points from each action type
MAX_MONTHLY_POST_POINTS = 30
MAX_MONTHLY_LIKE_POINTS = 15 
MAX_MONTHLY_COMMENT_POINTS = 15 
MAX_MONTHLY_REFERRAL_POINTS = 10 
MAX_MONTHLY_TIPPING_POINTS = 20
MAX_MONTHLY_CRYPTO_POINTS = 20

# Leaderboard bonus points
POINTS_FOR_WEEKLY_LEADER = 3
POINTS_FOR_MONTHLY_LEADER = 3

# Total possible monthly points
TOTAL_POSSIBLE_MONTHLY_POINTS = (
    MAX_MONTHLY_POST_POINTS +
    MAX_MONTHLY_LIKE_POINTS +
    MAX_MONTHLY_COMMENT_POINTS +
    MAX_MONTHLY_REFERRAL_POINTS +
    MAX_MONTHLY_TIPPING_POINTS +
    MAX_MONTHLY_CRYPTO_POINTS
)

# CATEGORY-WISE EMPATHY CONFIGURATION
# Percentage of non-qualified users to receive empathy rewards in each category
REWARD_PERCENTAGE_OF_INACTIVE = 0.10  # Top 10% of non-qualified users per category

# Weights for calculating category-specific empathy scores
HISTORICAL_SCORE_WEIGHTS = {
    "streak_at_reset": 0.5,        # Base streak component (applies to all categories)
    "lifetime_posts": 0.25,        # Weight for post-related empathy calculation
    "lifetime_likes": 0.08,        # Weight for like-related empathy calculation
    "lifetime_comments": 0.08,     # Weight for comment-related empathy calculation
    "lifetime_crypto": 0.09,       # Weight for crypto-related empathy calculation
    "lifetime_tipping": 0.05,      # Weight for tipping-related empathy calculation
    "lifetime_referrals": 0.05     # Weight for referral-related empathy calculation
}

# CATEGORY DEFINITIONS FOR API RESPONSES
REWARD_CATEGORIES = {
    'posts': {
        'name': 'Content Creation Rewards',
        'description': 'Rewards for users who create quality posts',
        'daily_requirement': POST_LIMIT_DAY,
        'point_value': POINTS_PER_POST
    },
    'likes': {
        'name': 'Engagement Rewards', 
        'description': 'Rewards for users who actively like content',
        'daily_requirement': LIKE_LIMIT_DAY,
        'point_value': POINTS_PER_LIKE
    },
    'comments': {
        'name': 'Discussion Rewards',
        'description': 'Rewards for users who participate in discussions',
        'daily_requirement': COMMENT_LIMIT_DAY,
        'point_value': POINTS_PER_COMMENT
    },
    'crypto': {
        'name': 'Crypto Activity Rewards',
        'description': 'Rewards for users who perform crypto transactions',
        'daily_requirement': CRYPTO_LIMIT_DAY,
        'point_value': POINTS_FOR_CRYPTO
    },
    'tipping': {
        'name': 'Community Support Rewards',
        'description': 'Rewards for users who tip other community members',
        'daily_requirement': TIPPING_LIMIT_DAY,
        'point_value': POINTS_FOR_TIPPING
    },
    'referrals': {
        'name': 'Growth Rewards',
        'description': 'Rewards for users who bring new members to the community',
        'daily_requirement': REFERRAL_LIMIT_DAY,
        'point_value': POINTS_PER_REFERRAL
    }
}