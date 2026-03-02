"""
Test query generator for TotalReclaw evaluation.

Generates 150 test queries across 6 categories based on real OpenClaw usage.
"""

from typing import List, Dict, Any, Set
from enum import Enum
import random


class QueryCategory(Enum):
    """Query categories based on OpenClaw usage patterns."""
    CONTEXTUAL_FACT = "contextual_fact"  # 30% - "What did Sarah say about X?"
    CONFIGURATION = "configuration"  # 20% - "What's my API config?"
    TEMPORAL = "temporal"  # 15% - "What did we do yesterday?"
    ERROR_SOLUTION = "error_solution"  # 15% - "How did we fix error X?"
    SEMANTIC = "semantic"  # 12% - "container orchestration" → Docker
    EXACT_KEYWORD = "exact_keyword"  # 8% - "sk-proj-abc123"


# Query distribution (150 queries total)
QUERY_DISTRIBUTION = {
    QueryCategory.CONTEXTUAL_FACT: 45,  # 30%
    QueryCategory.CONFIGURATION: 30,  # 20%
    QueryCategory.TEMPORAL: 22,  # 15%
    QueryCategory.ERROR_SOLUTION: 22,  # 15%
    QueryCategory.SEMANTIC: 18,  # 12%
    QueryCategory.EXACT_KEYWORD: 13,  # 8%
}


class QueryGenerator:
    """
    Generate test queries for evaluation.

    Example:
        >>> generator = QueryGenerator()
        >>> queries = generator.generate(num_queries=150)
        >>> queries[0]
        {
            'id': 'q001',
            'text': 'What did Sarah say about the API rate limit?',
            'category': 'contextual_fact'
        }
    """

    def __init__(self, seed: int = 42):
        """
        Initialize query generator.

        Args:
            seed: Random seed for reproducibility
        """
        random.seed(seed)
        self._query_counter = 0

        # Sample data for realistic queries
        self.people = ['Sarah', 'Mike', 'Jen', 'Tom', 'Lisa', 'John', 'Alex', 'Emma']
        self.companies = ['Acme Inc', 'TechCorp', 'DataSystems', 'CloudTech', 'StartupX']
        self.services = ['API', 'database', 'Redis cache', 'S3 bucket', 'CDN', 'load balancer']
        self.errors = ['429 rate limit', 'timeout error', 'CORS issue', 'deadlock', 'memory leak']
        self.concepts = [
            ('container orchestration', 'Docker'),
            ('CI/CD pipeline', 'GitHub Actions'),
            ('serverless computing', 'AWS Lambda'),
            ('document database', 'MongoDB'),
            ('message queue', 'RabbitMQ'),
            ('API gateway', 'Kong'),
            ('microservices', 'gRPC'),
            ('event streaming', 'Kafka')
        ]

    def generate(self, num_queries: int = 150) -> List[Dict[str, Any]]:
        """
        Generate test queries.

        Args:
            num_queries: Total number of queries to generate

        Returns:
            List of query dictionaries with 'id', 'text', 'category'
        """
        queries = []

        # Generate queries according to distribution
        for category, count in QUERY_DISTRIBUTION.items():
            category_queries = self._generate_category_queries(category, count)
            queries.extend(category_queries)

        # Shuffle queries
        random.shuffle(queries)

        # Assign sequential IDs
        for i, query in enumerate(queries, 1):
            query['id'] = f'q{i:03d}'

        return queries[:num_queries]

    def _generate_category_queries(
        self,
        category: QueryCategory,
        count: int
    ) -> List[Dict[str, Any]]:
        """Generate queries for a specific category."""
        generators = {
            QueryCategory.CONTEXTUAL_FACT: self._generate_contextual_queries,
            QueryCategory.CONFIGURATION: self._generate_configuration_queries,
            QueryCategory.TEMPORAL: self._generate_temporal_queries,
            QueryCategory.ERROR_SOLUTION: self._generate_error_queries,
            QueryCategory.SEMANTIC: self._generate_semantic_queries,
            QueryCategory.EXACT_KEYWORD: self._generate_exact_queries,
        }

        generator = generators.get(category)
        if generator:
            return generator(count)
        return []

    def _generate_contextual_queries(self, count: int) -> List[Dict[str, Any]]:
        """Generate contextual/fact retrieval queries."""
        templates = [
            "What did {person} say about {topic}?",
            "According to {person}, what's the best approach for {topic}?",
            "{person}'s opinion on {topic}",
            "What was the conclusion about {topic} that {person} mentioned?",
            "What did we decide regarding {person}'s suggestion about {topic}?",
        ]

        topics = [
            "the API rate limit",
            "database schema changes",
            "the deployment strategy",
            "error handling",
            "authentication flow",
            "the new feature timeline",
            "refactoring the codebase",
            "testing methodology",
            "performance optimization",
            "security concerns"
        ]

        queries = []
        for _ in range(count):
            template = random.choice(templates)
            person = random.choice(self.people)
            topic = random.choice(topics)

            queries.append({
                'text': template.format(person=person, topic=topic),
                'category': QueryCategory.CONTEXTUAL_FACT.value
            })

        return queries

    def _generate_configuration_queries(self, count: int) -> List[Dict[str, Any]]:
        """Generate configuration & setup queries."""
        templates = [
            "What's my API configuration?",
            "How do I connect to {service}?",
            "What are the {service} credentials?",
            "What's the base URL for the {service}?",
            "Show me the {service} connection string",
            "What's the timeout setting for {service}?",
            "How do I configure {service} in production?",
            "What's the {service} endpoint?",
        ]

        queries = []
        for _ in range(count):
            template = random.choice(templates)
            service = random.choice(self.services)

            queries.append({
                'text': template.format(service=service),
                'category': QueryCategory.CONFIGURATION.value
            })

        return queries

    def _generate_temporal_queries(self, count: int) -> List[Dict[str, Any]]:
        """Generate temporal/recent activity queries."""
        templates = [
            "What did we work on yesterday?",
            "What was decided in the last standup?",
            "What changed since last week?",
            "What bugs did we fix recently?",
            "What features were added this month?",
            "What was discussed in the {timeframe} meeting?",
            "What's the latest update on {topic}?",
            "What did {person} say in the last discussion?",
        ]

        timeframes = ['Monday', 'last sprint', 'the retrospective', 'yesterday', 'last week']
        topics = ['deployment', 'API changes', 'database migration', 'security fix']

        queries = []
        for _ in range(count):
            template = random.choice(templates)
            timeframe = random.choice(timeframes) if '{timeframe}' in template else None
            topic = random.choice(topics) if '{topic}' in template else None
            person = random.choice(self.people) if '{person}' in template else None

            if timeframe:
                text = template.format(timeframe=timeframe)
            elif topic:
                text = template.format(topic=topic)
            elif person:
                text = template.format(person=person)
            else:
                text = template

            queries.append({
                'text': text,
                'category': QueryCategory.TEMPORAL.value
            })

        return queries

    def _generate_error_queries(self, count: int) -> List[Dict[str, Any]]:
        """Generate error & solution lookup queries."""
        templates = [
            "How did we fix the {error}?",
            "What was the solution for {error}?",
            "{error} - what's the fix?",
            "We encountered {error} - what resolved it?",
            "Documentation for {error}",
            "Workaround for {error}",
        ]

        queries = []
        for _ in range(count):
            template = random.choice(templates)
            error = random.choice(self.errors)

            queries.append({
                'text': template.format(error=error),
                'category': QueryCategory.ERROR_SOLUTION.value
            })

        return queries

    def _generate_semantic_queries(self, count: int) -> List[Dict[str, Any]]:
        """Generate semantic/concept queries."""
        templates = [
            "{concept} tools",
            "How to implement {concept}?",
            "Best practices for {concept}",
            "{concept} setup guide",
            "Alternatives to {target} for {concept}",
            "Compare {concept} implementations",
        ]

        queries = []
        for _ in range(count):
            template = random.choice(templates)
            concept, target = random.choice(self.concepts)

            queries.append({
                'text': template.format(concept=concept, target=target),
                'category': QueryCategory.SEMANTIC.value,
                'expected_terms': [target]  # For validation
            })

        return queries

    def _generate_exact_queries(self, count: int) -> List[Dict[str, Any]]:
        """Generate exact/keyword queries."""
        # Generate realistic exact-match values
        api_keys = [
            "sk-proj-abc123xyz789",
            "ghp_xxxxxxxxxxxxxxxxxxxx",
            "AKIAIOSFODNN7EXAMPLE",
            "ya29.a0AfH6SMBx..."
        ]

        error_codes = [
            "ERR_CONNECTION_REFUSED",
            "HTTP 429",
            "ECONNRESET",
            "ETIMEDOUT",
            "502 Bad Gateway"
        ]

        uuids = [
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "123e4567-e89b-12d3-a456-426614174000"
        ]

        emails = [
            "sarahr@example.com",
            "api-techcorp@example.com",
            "support@service.com"
        ]

        exact_values = api_keys + error_codes + uuids + emails

        queries = []
        for i in range(count):
            value = exact_values[i % len(exact_values)]

            queries.append({
                'text': value,
                'category': QueryCategory.EXACT_KEYWORD.value,
                'expected_match': value
            })

        return queries

    def generate_for_dataset(
        self,
        documents: List[str],
        num_queries: int = 150
    ) -> List[Dict[str, Any]]:
        """
        Generate queries tailored to a specific dataset.

        Analyzes the documents to extract realistic entities and themes.

        Args:
            documents: List of document texts
            num_queries: Number of queries to generate

        Returns:
            List of query dictionaries
        """
        # Extract entities from documents
        entities = self._extract_entities_from_documents(documents)

        # Generate queries using extracted entities
        queries = []
        query_id = 1

        for category, count in QUERY_DISTRIBUTION.items():
            category_queries = self._generate_category_queries_with_entities(
                category, count, entities
            )
            for query in category_queries:
                query['id'] = f'q{query_id:03d}'
                queries.append(query)
                query_id += 1

        random.shuffle(queries)
        return queries[:num_queries]

    def _extract_entities_from_documents(
        self,
        documents: List[str]
    ) -> Dict[str, List[str]]:
        """Extract entities from documents for realistic query generation."""
        import re

        entities = {
            'people': set(),
            'emails': set(),
            'companies': set(),
            'error_codes': set(),
            'uuids': set(),
            'api_endpoints': set()
        }

        # Email pattern
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        # UUID pattern
        uuid_pattern = r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'
        # Error code pattern
        error_pattern = r'\b(E[H][A-Z0-9]+|HTTP\s+\d{3}|[45]\d{2}\s+[A-Z]+)'

        for doc in documents:
            entities['emails'].update(re.findall(email_pattern, doc))
            entities['uuids'].update(re.findall(uuid_pattern, doc))
            entities['error_codes'].update(re.findall(error_pattern, doc))

        # Convert sets to lists
        return {k: list(v) for k, v in entities.items()}

    def _generate_category_queries_with_entities(
        self,
        category: QueryCategory,
        count: int,
        entities: Dict[str, List[str]]
    ) -> List[Dict[str, Any]]:
        """Generate queries using extracted entities."""
        queries = []

        if category == QueryCategory.EXACT_KEYWORD:
            # Use actual extracted values
            exact_values = (
                entities.get('emails', [])[:5] +
                entities.get('error_codes', [])[:5] +
                entities.get('uuids', [])[:3]
            )

            for i in range(min(count, len(exact_values))):
                queries.append({
                    'text': exact_values[i],
                    'category': category.value
                })

        # For other categories, use base generator
        # (In production, would extract more entities)
        return queries if queries else self._generate_category_queries(category, count)


# Predefined query templates for reference
QUERY_TEMPLATES = {
    'contextual_fact': [
        "What did {person} say about {topic}?",
        "According to {person}, how should we handle {topic}?",
        "What was {person}'s suggestion for {topic}?"
    ],
    'configuration': [
        "What's my {service} configuration?",
        "How do I connect to {service}?",
        "What are the {service} credentials?"
    ],
    'temporal': [
        "What did we work on yesterday?",
        "What was decided in the last meeting?",
        "What changed since last week?"
    ],
    'error_solution': [
        "How did we fix {error}?",
        "What's the solution for {error}?",
        "{error} - what resolved it?"
    ],
    'semantic': [
        "{concept} implementation",
        "How to set up {concept}?",
        "Best practices for {concept}"
    ],
    'exact_keyword': [
        "{exact_value}",
        "Find {exact_value}",
        "Search for {exact_value}"
    ]
}
