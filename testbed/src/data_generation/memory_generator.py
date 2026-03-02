"""
Memory Generator Module

Generates synthetic memory data for TotalReclaw testbed using LLM.
Creates realistic OpenClaw-style memory entries with proper chunking,
metadata extraction, and entity recognition.
"""

import re
import hashlib
import yaml
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum
import json
import tiktoken


class MemoryCategory(Enum):
    """Memory categories matching OpenClaw usage patterns"""
    DAILY_CONVERSATION_LOGS = "daily_conversation_logs"
    EMAIL_THREADS = "email_threads"
    MEETING_NOTES = "meeting_notes"
    PERSONAL_PREFERENCES = "personal_preferences"
    TECHNICAL_DOCUMENTATION = "technical_documentation"
    CONFIGURATION_DETAILS = "configuration_details"


class SourceType(Enum):
    """Source file types in OpenClaw structure"""
    MEMORY_MD = "MEMORY.md"
    MEMORY_DAILY = "memory-daily"
    IMPORTED = "imported"


@dataclass
class Entity:
    """Extracted entity from memory content"""
    entity_type: str  # email, uuid, error_code, etc.
    value: str
    start_pos: int
    end_pos: int


@dataclass
class Memory:
    """A single memory chunk with all metadata"""
    id: str
    content: str
    category: MemoryCategory
    source_file: str
    source_type: SourceType
    chunk_index: int
    total_chunks: int
    line_start: int
    line_end: int
    created_at: datetime
    entities: List[Entity] = field(default_factory=list)
    embedding: Optional[np.ndarray] = None
    blind_indices: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category.value,
            "source_file": self.source_file,
            "source_type": self.source_type.value,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "created_at": self.created_at.isoformat(),
            "entities": [
                {
                    "type": e.entity_type,
                    "value": e.value,
                    "start_pos": e.start_pos,
                    "end_pos": e.end_pos
                }
                for e in self.entities
            ],
            "embedding": self.embedding.tolist() if self.embedding is not None else None,
            "blind_indices": self.blind_indices
        }


class EntityExtractor:
    """Extracts entities from memory content for blind indexing"""

    # Regex patterns for entity extraction
    PATTERNS = {
        "email": re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        ),
        "uuid": re.compile(
            r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
            r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'
        ),
        "api_key": re.compile(
            r'\b[A-Za-z0-9]{32,}\b'
        ),
        "error_code": re.compile(
            r'\b[1-5]\d{2}\b'
        ),
        "url": re.compile(
            r'https?://[^\s<>"{}|\\^`\[\]]+'
        ),
        "function_name": re.compile(
            r'\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.|::)[a-zA-Z_][a-zA-Z0-9_]*\b'
        ),
        "port": re.compile(
            r'\b:\d{4,5}\b'
        ),
        "timestamp": re.compile(
            r'\b\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}\b'
        )
    }

    @classmethod
    def extract_entities(cls, content: str) -> List[Entity]:
        """Extract all entities from content"""
        entities = []

        for entity_type, pattern in cls.PATTERNS.items():
            for match in pattern.finditer(content):
                entities.append(Entity(
                    entity_type=entity_type,
                    value=match.group(0),
                    start_pos=match.start(),
                    end_pos=match.end()
                ))

        # Sort by position and remove duplicates
        entities.sort(key=lambda e: e.start_pos)
        unique_entities = []
        seen = set()

        for entity in entities:
            key = (entity.entity_type, entity.value.lower())
            if key not in seen:
                seen.add(key)
                unique_entities.append(entity)

        return unique_entities


class MemoryChunker:
    """Chunks memory content respecting markdown boundaries"""

    # Markdown boundary patterns
    SECTION_HEADERS = re.compile(r'^#{1,6}\s+', re.MULTILINE)
    CODE_BLOCK_START = re.compile(r'^```[\w]*$', re.MULTILINE)

    def __init__(self, chunk_size_tokens: int = 400, overlap_tokens: int = 80):
        self.chunk_size_tokens = chunk_size_tokens
        self.overlap_tokens = overlap_tokens
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.encoding.encode(text))

    def find_chunk_boundaries(
        self,
        content: str,
        target_size: int,
        last_end: int = 0
    ) -> Tuple[int, int]:
        """Find optimal chunk boundaries respecting markdown"""

        # Get the target range
        target_end = last_end + target_size

        if target_end >= len(content):
            return last_end, len(content)

        # Look for markdown boundaries near target
        search_range = min(target_size // 4, 100)

        # Check for section headers first (preferred)
        for pattern in [self.SECTION_HEADERS, self.CODE_BLOCK_START]:
            best_match = None
            for match in pattern.finditer(content, max(0, target_end - search_range), target_end + search_range):
                if match.start() > last_end:
                    if best_match is None or abs(match.start() - target_end) < abs(best_match.start() - target_end):
                        best_match = match

            if best_match:
                return last_end, best_match.start()

        # Fall back to sentence boundaries
        sentence_end = content.rfind('.', last_end, target_end + search_range)
        if sentence_end > last_end + target_size // 2:
            return last_end, sentence_end + 1

        # Last resort: use target size
        return last_end, min(target_end, len(content))

    def chunk_content(
        self,
        content: str,
        source_file: str,
        source_type: SourceType,
        category: MemoryCategory
    ) -> List[Memory]:
        """Chunk content into multiple memories with overlap"""

        chunks = []
        lines = content.split('\n')

        current_line = 0
        chunk_index = 0
        position = 0
        content_len = len(content)

        # First pass: count total chunks needed
        estimated_chunks = max(1, self.count_tokens(content) // (self.chunk_size_tokens - self.overlap_tokens) + 1)

        while position < content_len:
            # Calculate chunk size based on tokens
            remaining = content_len - position
            chunk_size_chars = min(
                remaining,
                int(self.chunk_size_tokens * 4)  # Rough char-to-token ratio
            )

            start_pos, end_pos = self.find_chunk_boundaries(
                content,
                chunk_size_chars,
                position
            )

            chunk_content = content[start_pos:end_pos].strip()

            if not chunk_content:
                break

            # Track line numbers
            line_start = current_line
            line_end = line_start + chunk_content.count('\n')

            # Generate ID
            chunk_id = hashlib.sha256(
                f"{source_file}:{chunk_index}:{chunk_content[:100]}".encode()
            ).hexdigest()[:16]

            # Extract entities
            entities = EntityExtractor.extract_entities(chunk_content)

            # Calculate creation date (spread across Jan-Feb 2026)
            base_date = datetime(2026, 1, 1)
            days_offset = chunk_index * 2
            created_at = base_date + timedelta(days=days_offset)

            memory = Memory(
                id=chunk_id,
                content=chunk_content,
                category=category,
                source_file=source_file,
                source_type=source_type,
                chunk_index=chunk_index,
                total_chunks=estimated_chunks,
                line_start=line_start,
                line_end=line_end,
                created_at=created_at,
                entities=entities
            )

            chunks.append(memory)

            # Move to next chunk with overlap
            overlap_chars = min(
                len(chunk_content) // 2,  # Max 50% overlap to prevent infinite loops
                int(self.overlap_tokens * 4)
            )
            # Ensure we make progress
            new_position = end_pos - overlap_chars
            if new_position <= position:
                new_position = position + (len(chunk_content) // 2)
            position = new_position
            current_line = line_end
            chunk_index += 1

        # Update total chunks count
        for chunk in chunks:
            chunk.total_chunks = len(chunks)

        return chunks


class MemoryGenerator:
    """Main memory generation orchestrator"""

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "categories.yaml"

        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.chunker = MemoryChunker()

    def get_category_config(self, category: MemoryCategory) -> Dict[str, Any]:
        """Get configuration for a category"""
        return self.config["categories"][category.value]

    def generate_memories_from_llm(
        self,
        category: MemoryCategory,
        count: int,
        prompt_template: str,
        llm_client: Any = None
    ) -> List[Memory]:
        """
        Generate memories from LLM output

        Args:
            category: The memory category
            count: Number of memory entries to generate
            prompt_template: Prompt template for LLM
            llm_client: LLM client (optional, returns template if None)

        Returns:
            List of Memory objects
        """

        # For now, generate template-based content
        # In production, this would call an LLM API
        all_memories = []

        category_config = self.get_category_config(category)
        source_type = SourceType[category_config["source_file"].replace("-", "_").replace(".", "_").upper()]

        # Generate sample dates across Jan-Feb 2026
        start_date = datetime(2026, 1, 1)

        for i in range(count):
            # Generate source file path
            date_offset = timedelta(days=i // 10)  # 10 entries per file
            file_date = start_date + date_offset

            if source_type == SourceType.MEMORY_DAILY:
                source_file = f"memory/{file_date.strftime('%Y-%m-%d')}.md"
            else:
                source_file = "MEMORY.md"

            # Generate realistic content based on category
            content = self._generate_sample_content(category, i, file_date)

            # Chunk the content
            chunks = self.chunker.chunk_content(
                content,
                source_file,
                source_type,
                category
            )

            all_memories.extend(chunks)

        return all_memories

    def _generate_sample_content(
        self,
        category: MemoryCategory,
        index: int,
        date: datetime
    ) -> str:
        """Generate sample memory content for testing"""

        samples = {
            MemoryCategory.DAILY_CONVERSATION_LOGS: self._sample_conversation_log(index, date),
            MemoryCategory.EMAIL_THREADS: self._sample_email_thread(index, date),
            MemoryCategory.MEETING_NOTES: self._sample_meeting_notes(index, date),
            MemoryCategory.PERSONAL_PREFERENCES: self._sample_personal_preferences(),
            MemoryCategory.TECHNICAL_DOCUMENTATION: self._sample_technical_documentation(),
            MemoryCategory.CONFIGURATION_DETAILS: self._sample_configuration_details()
        }

        return samples.get(category, "")

    def _sample_conversation_log(self, index: int, date: datetime) -> str:
        """Generate sample conversation log"""
        times = ["9:15 AM", "10:30 AM", "2:45 PM", "4:20 PM"]
        topics = [
            ("API Rate Limiting Fix", "429", "https://api.stripe.com/v1"),
            ("Database Query Optimization", "timeout", "PostgreSQL"),
            ("React State Management", "Zustand", "Redux"),
            ("Authentication Flow", "OAuth", "JWT"),
        ]

        time = times[index % len(times)]
        topic, error, service = topics[index % len(topics)]

        return f"""## memory/{date.strftime('%Y-%m-%d')}.md

### {time} - {topic}
**User:** We're getting {error} errors when calling {service}. The rate limit is 100 requests per minute.
**Assistant:** I'll implement exponential backoff with jitter. Let's add rate-limiting middleware to handle the {error} responses.

**User:** The endpoint is https://api.example.com/v1/graphql and we need to cache responses for 5 minutes.
**Assistant:** Got it. I'll configure Redis caching with a 300-second TTL for all GraphQL queries.

### {time} - Code Structure Discussion
**User:** Should we use /src/components for React components and /src/lib for utilities?
**Assistant:** Yes, and let's use TypeScript strict mode with kebab-case filenames like UserProfileCard.tsx.

**User:** What about the API client? Should we use axios or fetch?
**Assistant:** Let's use axios with interceptors for automatic token refresh. The base URL is https://api.example.com/v1.

### {time} - Error Debugging
**User:** I'm getting error code {error} when trying to authenticate. The user ID is a828e60-7b4a-4f3d-9e2a-1c5b8d9e6f3a.
**Assistant:** That's a rate limit error. Let me check the memorySearch.query.hybrid function - it might be making too many concurrent requests.

**User:** The error happens at line 42 in AuthService.ts. Here's the stack trace:
```
Error: Request failed with status code 429
    at axios.request (AuthService.ts:42)
    at memorySearch.query.hybrid (search.ts:156)
```
**Assistant:** I see the issue. We need to implement request queuing. Let me add a rate limiter.

"""

    def _sample_email_thread(self, index: int, date: datetime) -> str:
        """Generate sample email thread"""
        senders = [
            ("Sarah Rodriguez", "sarah.r@techcorp.com"),
            ("Mike Chen", "mike.chen@company.io"),
            ("Jennifer Lopez", "jen.lopez@company.io"),
            ("David Kim", "david.kim@company.io"),
        ]

        sender, email = senders[index % len(senders)]
        subjects = [
            "API Security Update - Key Rotation Required",
            "Deployment Schedule for v2.3.0",
            "Code Review: Authentication Module Refactor",
            "Incident Post-Mortem: Database Outage",
        ]

        subject = subjects[index % len(subjects)]

        return f"""## Email Thread: {subject}
**Date:** {date.strftime('%Y-%m-%d')} 14:{30 + index:02d}
**From:** {sender} <{email}>
**To:** dev-team@company.io
**CC:** security@company.io, ops@company.io

Hi team,

I wanted to follow up on our discussion about {subject.lower()}. The changes need to be deployed to production by Friday.

Key points:
- API endpoint: https://api.example.com/v1/auth
- New rate limit: 1000 requests/minute (increased from 100)
- Error code 429 will include Retry-After header
- Database migration required for users table

Please review the PR at github.com/company/repo/pull/1234.

Best,
{sender}

---
**Reply from:** Mike Chen <mike.chen@company.io>
**Date:** {date.strftime('%Y-%m-%d')} 15:45

Thanks for the update {sender.split()[0]}. A few questions:

1. Will this affect the Stripe integration (api.stripe.com/v1)?
2. Do we need to update environment variables for API_BASE_URL?
3. What's the rollback plan if something breaks?

The configuration should be:
```
API_BASE_URL=https://api.example.com/v1
API_TIMEOUT=30000
RATE_LIMIT=1000
```

---
**Reply from:** Sarah Rodriguez <sarah.r@techcorp.com>
**Date:** {date.strftime('%Y-%m-%d')} 16:20

Good questions Mike:

1. Stripe integration is unaffected - it uses a separate client
2. Yes, update API_BASE_URL in staging first
3. Rollback plan: revert to previous docker image tag (v2.2.1)

Deployment window is Saturday 2 AM UTC. The database migration ID is db_20260215_auth_update.

"""

    def _sample_meeting_notes(self, index: int, date: datetime) -> str:
        """Generate sample meeting notes"""
        meeting_types = [
            "Daily Standup",
            "Sprint Planning",
            "1:1 with Manager",
            "Technical Design Review",
        ]

        meeting_type = meeting_types[index % len(meeting_types)]

        return f"""## Meeting: {meeting_type} - {date.strftime('%B %d, %Y')}
**Date:** {date.strftime('%Y-%m-%d')} 10:00
**Attendees:**
- Sarah Rodriguez (sarah.r@techcorp.com) - Backend Lead
- Mike Chen (mike.chen@company.io) - Frontend Lead
- Jennifer Lopez (jen.lopez@company.io) - Product Manager
- David Kim (david.kim@company.io) - DevOps Engineer
**Duration:** 45 minutes

### Agenda
- Review current sprint progress
- Discuss API rate limiting issues (error 429)
- Plan deployment for v2.3.0
- Address database query timeouts

### Discussion

**Sarah:** The backend team is working on fixing the rate limiting issue. We're seeing 429 errors when the load exceeds 100 req/min. The fix involves implementing exponential backoff.

**Mike:** Frontend is ready for the new authentication flow. We're using OAuth 2.0 with PKCE. The callback URL is https://app.company.io/auth/callback.

**Jennifer:** Product team needs the feature deployed by Friday. The key requirement is the user profile update endpoint: PUT /api/v1/users/{id}.

**David:** DevOps has set up the staging environment in us-west-2. We're using PostgreSQL 15 with pgvector. The connection string is in the AWS Secrets Manager.

### Action Items
- [ ] Sarah: Implement rate limiting by Friday - sarah.r@techcorp.com
- [ ] Mike: Update API documentation with new endpoints - mike.chen@company.io
- [ ] David: Deploy staging environment by tomorrow - david.kim@company.io
- [ ] Jennifer: Write product requirements for v2.4.0 - jen.lopez@company.io

### Next Meeting
Technical Design Review: Wednesday, 10 AM EST
Topic: Microservices architecture migration

"""

    def _sample_personal_preferences(self) -> str:
        """Generate sample personal preferences"""
        return """## Personal Preferences

### Work Schedule
- Standup: 10:00 AM EST daily with frontend team
- 1:1 with manager: Thursdays at 3:00 PM
- Focus hours: 9 AM - 12 PM (no meetings scheduled)
- Lunch break: 12:30 PM - 1:30 PM

### Environment Setup
- Local dev server: http://localhost:3000
- API server: http://localhost:8080
- Database: PostgreSQL 15 on port 5432
- Redis: localhost:6379
- GraphQL playground: http://localhost:8080/graphql

### Team Contacts
- Backend lead: Sarah Rodriguez (sarah.r@techcorp.com)
- Frontend lead: Mike Chen (mike.chen@company.io)
- Product manager: Jennifer Lopez (jen.lopez@company.io)
- DevOps: David Kim (david.kim@company.io)
- Security: Alex Turner (alex.turner@company.io)

### Code Preferences
- TypeScript strict mode enabled
- Prettier for formatting (2 spaces)
- ESLint rules extended from airbnb-typescript
- Git commit format: conventional commits (feat:, fix:, docs:)
- Branch naming: feature/ticket-name, fix/bug-description

### Development Workflow
- Feature branches from main
- PR requires at least 1 approval
- CI/CD runs on every push
- Deploy to staging after merge to main
- Production deploys on Tuesdays and Fridays

"""

    def _sample_technical_documentation(self) -> str:
        """Generate sample technical documentation"""
        return """## Technical Documentation

### API Configuration
- **Base URL:** https://api.example.com/v1
- **GraphQL Endpoint:** https://api.example.com/v1/graphql
- **Authentication:** Bearer token (stored in AWS Secrets Manager)
- **Rate Limit:** 100 requests/minute (429 response with Retry-After header)
- **Timeout:** 30 seconds
- **Retry Strategy:** Exponential backoff with jitter

### Third-Party Services

**Stripe API**
- Base URL: https://api.stripe.com/v1
- Webhook endpoint: /api/v1/webhooks/stripe
- Test mode secret key: sk_test_51AbCdEf...
- Live mode secret key: sk_live_51AbCdEf...

**AWS S3**
- Region: us-east-1
- Bucket: company-documents
- Public access: disabled
- CDN: CloudFront (distribution ID: E1234567890ABC)

**GitHub Integration**
- API base: https://api.github.com/repos/company/repo
- Webhook secret: ghp_xxxxxxxxxxxx
- OAuth app ID: 123456

### Database Schema

```sql
-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Sessions table
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for email lookups
CREATE INDEX idx_users_email ON users(email);
```

### Deployment

**Environment Variables:**
```
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=your-secret-key
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

**CI/CD Pipeline:**
- Trigger: Push to main branch
- Build: Docker image (Dockerfile in repo root)
- Test: pytest with coverage
- Deploy: GitHub Actions workflow

"""

    def _sample_configuration_details(self) -> str:
        """Generate sample configuration details"""
        return """## Configuration Details

### API Keys (Placeholder Format)
```
# OpenAI API
OPENAI_API_KEY=sk-proj-abc123def456...
OPENAI_MODEL=gpt-4-turbo
OPENAI_MAX_TOKENS=4096

# Stripe
STRIPE_SECRET_KEY=pk_live_51AbCdEfGhIjKlMnOpQrStUvWxYz1234567890
STRIPE_WEBHOOK_SECRET=whsec_abc123def456...

# GitHub
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_REPO=company/private-repo

# AWS
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_REGION=us-east-1
AWS_S3_BUCKET=company-data
```

### Connection Strings
```
# PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/production
POOL_SIZE=20
MAX_OVERFLOW=10

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_MAX_CONNECTIONS=50

# MongoDB
MONGODB_URI=mongodb://user:pass@localhost:27017/dbname?authSource=admin

# RabbitMQ
RABBITMQ_URL=amqp://user:password@localhost:5672/
```

### Service Endpoints
```
# Internal API
API_BASE_URL=https://api.example.com/v1
API_TIMEOUT=30000
API_RETRY_ATTEMPTS=3

# External Services
STRIPE_API_URL=https://api.stripe.com/v1
GITHUB_API_URL=https://api.github.com
SLACK_API_URL=https://slack.com/api

# Webhooks
WEBHOOK_URL=https://example.com/api/webhooks
WEBHOOK_SECRET=your-webhook-secret

# CDN
CDN_URL=https://cdn.example.com
CDD_BUCKET=https://s3.us-east-1.amazonaws.com/my-bucket
```

### Feature Flags
```
FEATURE_AUTH_V2=true
FEATURE_RATE_LIMITING=true
FEATURE_CACHING_ENABLED=true
FEATURE_ANALYTICS=false
```

### Server Configuration
```
SERVER_PORT=8080
SERVER_HOST=0.0.0.0
NODE_ENV=production
LOG_LEVEL=info
CORS_ORIGIN=https://app.example.com
```

"""


def generate_memories(
    count_per_category: Dict[str, int],
    output_path: Optional[Path] = None
) -> List[Memory]:
    """
    Generate synthetic memories following OpenClaw structure

    Args:
        count_per_category: Dictionary mapping category names to desired counts
        output_path: Optional path to save generated memories as JSON

    Returns:
        List of generated Memory objects
    """
    generator = MemoryGenerator()
    all_memories = []

    for category_str, count in count_per_category.items():
        category = MemoryCategory(category_str)
        memories = generator.generate_memories_from_llm(
            category=category,
            count=count,
            prompt_template=""  # Using built-in templates
        )
        all_memories.extend(memories)

    # Save to file if path provided
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "memories": [m.to_dict() for m in all_memories],
            "total_count": len(all_memories),
            "categories": count_per_category,
            "generated_at": datetime.now().isoformat()
        }

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

    return all_memories


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate synthetic memory data")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--count", "-c", type=int, default=1500, help="Total memories to generate")

    args = parser.parse_args()

    # Default distribution
    distribution = {
        "daily_conversation_logs": int(args.count * 0.30),
        "email_threads": int(args.count * 0.25),
        "meeting_notes": int(args.count * 0.15),
        "personal_preferences": int(args.count * 0.15),
        "technical_documentation": int(args.count * 0.10),
        "configuration_details": int(args.count * 0.05),
    }

    memories = generate_memories(distribution, args.output)

    print(f"Generated {len(memories)} memory chunks")
    for category, count in distribution.items():
        actual = sum(1 for m in memories if m.category.value == category)
        print(f"  {category}: {actual} chunks (target: {count})")
