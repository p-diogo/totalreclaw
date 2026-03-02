"""
Query templates for test query generation.

Reference templates organized by category.
"""

QUERY_TEMPLATES = {
    'contextual_fact': {
        'description': 'Queries about what someone said or decided (30% of queries)',
        'examples': [
            "What did Sarah say about the API rate limit?",
            "According to Mike, what's the best approach for database schema changes?",
            "What was Tom's opinion on the deployment strategy?",
            "What did we decide regarding Jen's suggestion about authentication?",
            "What did Lisa mention about the new feature timeline?"
        ],
        'templates': [
            "What did {person} say about {topic}?",
            "According to {person}, what's the best approach for {topic}?",
            "{person}'s opinion on {topic}",
            "What was the conclusion about {topic} that {person} mentioned?",
            "What did we decide regarding {person}'s suggestion about {topic}?"
        ],
        'variables': {
            'person': ['Sarah', 'Mike', 'Jen', 'Tom', 'Lisa', 'John', 'Alex', 'Emma'],
            'topic': [
                'the API rate limit', 'database schema changes', 'the deployment strategy',
                'error handling', 'authentication flow', 'the new feature timeline',
                'refactoring the codebase', 'testing methodology', 'performance optimization',
                'security concerns', 'CI/CD pipeline', 'microservices architecture'
            ]
        }
    },

    'configuration': {
        'description': 'Queries about configuration settings and credentials (20% of queries)',
        'examples': [
            "What's my API configuration?",
            "How do I connect to the Redis cache?",
            "What are the database credentials?",
            "What's the base URL for the API?",
            "Show me the S3 bucket connection string"
        ],
        'templates': [
            "What's my API configuration?",
            "How do I connect to {service}?",
            "What are the {service} credentials?",
            "What's the base URL for the {service}?",
            "Show me the {service} connection string",
            "What's the timeout setting for {service}?",
            "How do I configure {service} in production?",
            "What's the {service} endpoint?"
        ],
        'variables': {
            'service': [
                'API', 'database', 'Redis cache', 'S3 bucket', 'CDN',
                'load balancer', 'message queue', 'email service'
            ]
        }
    },

    'temporal': {
        'description': 'Queries about recent activity and time-based information (15% of queries)',
        'examples': [
            "What did we work on yesterday?",
            "What was decided in the last standup?",
            "What changed since last week?",
            "What bugs did we fix recently?",
            "What features were added this month?"
        ],
        'templates': [
            "What did we work on yesterday?",
            "What was decided in the last standup?",
            "What changed since last week?",
            "What bugs did we fix recently?",
            "What features were added this month?",
            "What was discussed in the {timeframe} meeting?",
            "What's the latest update on {topic}?",
            "What did {person} say in the last discussion?"
        ],
        'variables': {
            'timeframe': ['Monday', 'last sprint', 'the retrospective', 'yesterday', 'last week'],
            'topic': ['deployment', 'API changes', 'database migration', 'security fix'],
            'person': ['Sarah', 'Mike', 'Jen', 'Tom', 'Lisa']
        }
    },

    'error_solution': {
        'description': 'Queries about errors and their solutions (15% of queries)',
        'examples': [
            "How did we fix the 429 rate limit error?",
            "What was the solution for the timeout error?",
            "CORS issue - what's the fix?",
            "We encountered a deadlock - what resolved it?",
            "Documentation for memory leak"
        ],
        'templates': [
            "How did we fix the {error}?",
            "What was the solution for {error}?",
            "{error} - what's the fix?",
            "We encountered {error} - what resolved it?",
            "Documentation for {error}",
            "Workaround for {error}"
        ],
        'variables': {
            'error': [
                '429 rate limit', 'timeout error', 'CORS issue',
                'deadlock', 'memory leak', 'connection refused',
                'null pointer exception', 'race condition'
            ]
        }
    },

    'semantic': {
        'description': 'Concept-based queries requiring semantic understanding (12% of queries)',
        'examples': [
            "container orchestration tools",
            "How to implement CI/CD pipeline?",
            "Best practices for serverless computing",
            "document database setup guide",
            "message queue implementation"
        ],
        'templates': [
            "{concept} tools",
            "How to implement {concept}?",
            "Best practices for {concept}",
            "{concept} setup guide",
            "Alternatives to {target} for {concept}",
            "Compare {concept} implementations"
        ],
        'variables': {
            'concept_target_pairs': [
                ('container orchestration', 'Docker'),
                ('CI/CD pipeline', 'GitHub Actions'),
                ('serverless computing', 'AWS Lambda'),
                ('document database', 'MongoDB'),
                ('message queue', 'RabbitMQ'),
                ('API gateway', 'Kong'),
                ('microservices communication', 'gRPC'),
                ('event streaming', 'Kafka')
            ]
        }
    },

    'exact_keyword': {
        'description': 'Queries requiring exact keyword matching (8% of queries)',
        'examples': [
            "sk-proj-abc123xyz789",
            "ERR_CONNECTION_REFUSED",
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "sarahr@example.com",
            "AKIAIOSFODNN7EXAMPLE"
        ],
        'templates': [
            "{exact_value}"
        ],
        'variables': {
            'api_keys': [
                "sk-proj-abc123xyz789",
                "ghp_xxxxxxxxxxxxxxxxxxxx",
                "AKIAIOSFODNN7EXAMPLE",
                "ya29.a0AfH6SMBx..."
            ],
            'error_codes': [
                "ERR_CONNECTION_REFUSED",
                "HTTP 429",
                "ECONNRESET",
                "ETIMEDOUT",
                "502 Bad Gateway"
            ],
            'uuids': [
                "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "123e4567-e89b-12d3-a456-426614174000"
            ],
            'emails': [
                "sarahr@example.com",
                "api-techcorp@example.com",
                "support@service.com"
            ]
        }
    }
}
