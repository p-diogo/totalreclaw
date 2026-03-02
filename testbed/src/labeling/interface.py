"""
Ground truth labeling interface using Flask.

Provides a web interface for evaluators to label query-document pairs.
"""

from typing import List, Dict, Set, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import random

from flask import Flask, render_template, request, jsonify, redirect, url_for


@dataclass
class QueryDocumentPair:
    """A query-document pair to be labeled."""
    query_id: str
    query_text: str
    query_category: str
    doc_id: int
    doc_text: str
    doc_source: str  # MEMORY.md or memory/YYYY-MM-DD.md


@dataclass
class Label:
    """A relevance label from an evaluator."""
    evaluator_id: str
    query_id: str
    doc_id: int
    is_relevant: bool
    timestamp: datetime = field(default_factory=datetime.now)
    notes: str = ""


class LabelingInterface:
    """
    Web-based labeling interface for ground truth annotation.

    Example:
        >>> interface = LabelingInterface(
        ...     queries=[...],
        ...     documents={...},
        ...     evaluator_ids=['eval1', 'eval2', 'eval3']
        ... )
        >>> interface.run(port=5000)
    """

    def __init__(
        self,
        queries: List[Dict[str, Any]],
        documents: Dict[int, str],
        evaluator_ids: List[str],
        labels_per_query: int = 20,
        output_dir: str = "./data/ground_truth"
    ):
        """
        Initialize labeling interface.

        Args:
            queries: List of query dicts with 'id', 'text', 'category'
            documents: Dict mapping doc_id to document text
            evaluator_ids: List of evaluator identifiers
            labels_per_query: Number of documents to show per query
            output_dir: Directory to save labels
        """
        self.queries = queries
        self.documents = documents
        self.evaluator_ids = evaluator_ids
        self.labels_per_query = labels_per_query
        self.output_dir = output_dir

        # Load existing labels
        self.labels = self._load_existing_labels()

        # Create Flask app
        self.app = Flask(__name__)
        self.app.secret_key = 'totalreclaw-labeling-secret-key'

        # Setup routes
        self._setup_routes()

    def _load_existing_labels(self) -> Dict[str, Dict[str, Label]]:
        """Load existing labels from files."""
        labels = {}
        for evaluator_id in self.evaluator_ids:
            labels[evaluator_id] = {}
            # Try to load from file
            filepath = f"{self.output_dir}/labels_{evaluator_id}.json"
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    for label_data in data:
                        label = Label(
                            evaluator_id=label_data['evaluator_id'],
                            query_id=label_data['query_id'],
                            doc_id=label_data['doc_id'],
                            is_relevant=label_data['is_relevant'],
                            timestamp=datetime.fromisoformat(label_data['timestamp']),
                            notes=label_data.get('notes', '')
                        )
                        key = f"{label.query_id}_{label.doc_id}"
                        labels[evaluator_id][key] = label
            except FileNotFoundError:
                pass

        return labels

    def _setup_routes(self):
        """Setup Flask routes."""

        @self.app.route('/')
        def index():
            """Home page - select evaluator."""
            return render_template('index.html', evaluators=self.evaluator_ids)

        @self.app.route('/evaluator/<evaluator_id>')
        def evaluator_dashboard(evaluator_id):
            """Evaluator dashboard."""
            if evaluator_id not in self.evaluator_ids:
                return "Invalid evaluator ID", 400

            # Calculate progress
            total = len(self.queries) * self.labels_per_query
            labeled = len(self.labels.get(evaluator_id, {}))
            progress = (labeled / total * 100) if total > 0 else 0

            return render_template(
                'dashboard.html',
                evaluator_id=evaluator_id,
                queries=self.queries,
                progress=progress,
                labeled=labeled,
                total=total
            )

        @self.app.route('/evaluator/<evaluator_id>/label')
        def label_page(evaluator_id):
            """Labeling page."""
            if evaluator_id not in self.evaluator_ids:
                return "Invalid evaluator ID", 400

            query_id = request.args.get('query_id')

            # Get next unlabeled query if not specified
            if query_id is None:
                query_id = self._get_next_query(evaluator_id)

            if query_id is None:
                return redirect(url_for('evaluator_dashboard', evaluator_id=evaluator_id))

            # Get query info
            query = next((q for q in self.queries if q['id'] == query_id), None)
            if not query:
                return "Query not found", 404

            # Get documents to label
            doc_pairs = self._get_documents_for_query(query_id, evaluator_id)

            return render_template(
                'label.html',
                evaluator_id=evaluator_id,
                query=query,
                doc_pairs=doc_pairs,
                progress=self._get_query_progress(evaluator_id, query_id)
            )

        @self.app.route('/api/label', methods=['POST'])
        def submit_labels():
            """Submit labels."""
            data = request.json
            evaluator_id = data.get('evaluator_id')
            labels_data = data.get('labels', [])

            if evaluator_id not in self.evaluator_ids:
                return jsonify({'error': 'Invalid evaluator ID'}), 400

            # Save labels
            for label_item in labels_data:
                label = Label(
                    evaluator_id=evaluator_id,
                    query_id=label_item['query_id'],
                    doc_id=label_item['doc_id'],
                    is_relevant=label_item['is_relevant'],
                    notes=label_item.get('notes', '')
                )
                key = f"{label.query_id}_{label.doc_id}"
                self.labels[evaluator_id][key] = label

            # Save to file
            self._save_labels(evaluator_id)

            return jsonify({'success': True, 'labeled_count': len(labels_data)})

        @self.app.route('/api/export/<evaluator_id>')
        def export_labels_api(evaluator_id):
            """Export labels for an evaluator."""
            if evaluator_id not in self.evaluator_ids:
                return jsonify({'error': 'Invalid evaluator ID'}), 400

            labels_list = [
                {
                    'query_id': label.query_id,
                    'doc_id': label.doc_id,
                    'is_relevant': label.is_relevant,
                    'timestamp': label.timestamp.isoformat(),
                    'notes': label.notes
                }
                for label in self.labels.get(evaluator_id, {}).values()
            ]

            return jsonify({'labels': labels_list})

    def _get_next_query(self, evaluator_id: str) -> Optional[str]:
        """Get next query that needs labeling."""
        evaluator_labels = self.labels.get(evaluator_id, {})

        for query in self.queries:
            labeled_count = sum(
                1 for key in evaluator_labels.keys()
                if key.startswith(f"{query['id']}_")
            )
            if labeled_count < self.labels_per_query:
                return query['id']

        return None

    def _get_documents_for_query(
        self,
        query_id: str,
        evaluator_id: str
    ) -> List[QueryDocumentPair]:
        """
        Get documents to label for a query.

        Strategy: Mix of likely relevant and random documents.
        """
        evaluator_labels = self.labels.get(evaluator_id, {})

        # Get already labeled doc IDs for this query
        labeled_doc_ids = {
            int(key.split('_')[1])
            for key in evaluator_labels.keys()
            if key.startswith(f"{query_id}_")
        }

        # Get query
        query = next((q for q in self.queries if q['id'] == query_id), None)
        if not query:
            return []

        # Select documents
        # For testbed, we'll use a mix of:
        # 1. Some documents containing query terms (likely relevant)
        # 2. Some random documents
        pairs = []

        # Simple keyword matching for "likely relevant" docs
        query_terms = set(query['text'].lower().split())

        candidate_docs = []
        for doc_id, doc_text in self.documents.items():
            if doc_id in labeled_doc_ids:
                continue

            # Check if document contains query terms
            doc_lower = doc_text.lower()
            term_count = sum(1 for term in query_terms if term in doc_lower)

            candidate_docs.append((doc_id, doc_text, term_count))

        # Sort by term count (likely relevant first)
        candidate_docs.sort(key=lambda x: x[2], reverse=True)

        # Select top 10 likely relevant + 10 random
        n_to_select = min(self.labels_per_query, len(candidate_docs))
        likely_relevant = candidate_docs[:min(10, n_to_select)]
        remaining = candidate_docs[len(likely_relevant):]
        random_selection = random.sample(remaining, min(n_to_select - len(likely_relevant), len(remaining)))

        selected = likely_relevant + random_selection

        for doc_id, doc_text, _ in selected:
            pairs.append(QueryDocumentPair(
                query_id=query_id,
                query_text=query['text'],
                query_category=query.get('category', 'unknown'),
                doc_id=doc_id,
                doc_text=doc_text[:1000],  # Truncate for display
                doc_source="memory"  # Simplified
            ))

        return pairs

    def _get_query_progress(self, evaluator_id: str, query_id: str) -> Dict[str, int]:
        """Get labeling progress for a specific query."""
        evaluator_labels = self.labels.get(evaluator_id, {})

        labeled = sum(
            1 for key in evaluator_labels.keys()
            if key.startswith(f"{query_id}_")
        )

        return {
            'labeled': labeled,
            'total': self.labels_per_query,
            'percent': int(labeled / self.labels_per_query * 100) if self.labels_per_query > 0 else 0
        }

    def _save_labels(self, evaluator_id: str):
        """Save labels to file."""
        import os
        os.makedirs(self.output_dir, exist_ok=True)

        filepath = f"{self.output_dir}/labels_{evaluator_id}.json"

        labels_list = [
            {
                'evaluator_id': label.evaluator_id,
                'query_id': label.query_id,
                'doc_id': label.doc_id,
                'is_relevant': label.is_relevant,
                'timestamp': label.timestamp.isoformat(),
                'notes': label.notes
            }
            for label in self.labels.get(evaluator_id, {}).values()
        ]

        with open(filepath, 'w') as f:
            json.dump(labels_list, f, indent=2)

    def run(self, host='0.0.0.0', port=5000, debug=True):
        """Run the labeling interface."""
        # Create templates directory
        import os
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        os.makedirs(template_dir, exist_ok=True)

        # Create templates
        self._create_templates(template_dir)

        self.app.run(host=host, port=port, debug=debug)

    def _create_templates(self, template_dir: str):
        """Create HTML templates."""
        index_html = '''<!DOCTYPE html>
<html>
<head>
    <title>TotalReclaw Ground Truth Labeling</title>
    <style>
        body { font-family: system-ui, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; }
        h1 { color: #333; }
        .evaluator-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; margin-top: 24px; }
        .evaluator-card { border: 1px solid #ddd; border-radius: 8px; padding: 16px; cursor: pointer; transition: box-shadow 0.2s; }
        .evaluator-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .evaluator-card h3 { margin: 0 0 8px 0; color: #2563eb; }
    </style>
</head>
<body>
    <h1>TotalReclaw Ground Truth Labeling</h1>
    <p>Select your evaluator ID to continue:</p>
    <div class="evaluator-grid">
        {% for evaluator in evaluators %}
        <a href="/evaluator/{{ evaluator }}" class="evaluator-card">
            <h3>{{ evaluator }}</h3>
        </a>
        {% endfor %}
    </div>
</body>
</html>'''

        dashboard_html = '''<!DOCTYPE html>
<html>
<head>
    <title>Dashboard - {{ evaluator_id }}</title>
    <style>
        body { font-family: system-ui, sans-serif; max-width: 1000px; margin: 40px auto; padding: 0 20px; }
        .progress-bar { width: 100%; height: 24px; background: #e5e7eb; border-radius: 12px; overflow: hidden; margin: 16px 0; }
        .progress-fill { height: 100%; background: #10b981; transition: width 0.3s; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; }
        .query-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px; margin-top: 24px; }
        .query-card { border: 1px solid #ddd; border-radius: 8px; padding: 12px; cursor: pointer; }
        .query-card:hover { background: #f9fafb; }
        .query-card h4 { margin: 0 0 8px 0; }
        .query-card .category { color: #6b7280; font-size: 14px; }
    </style>
</head>
<body>
    <h1>Dashboard: {{ evaluator_id }}</h1>
    <p>Progress: {{ labeled }} / {{ total }} queries labeled</p>
    <div class="progress-bar">
        <div class="progress-fill" style="width: {{ progress }}%">{{ progress|round(1) }}%</div>
    </div>
    <div class="query-list">
        {% for query in queries %}
        <a href="/evaluator/{{ evaluator_id }}/label?query_id={{ query.id }}" class="query-card">
            <h4>{{ query.text[:50] }}{% if query.text|length > 50 %}...{% endif %}</h4>
            <span class="category">{{ query.category }}</span>
        </a>
        {% endfor %}
    </div>
</body>
</html>'''

        label_html = '''<!DOCTYPE html>
<html>
<head>
    <title>Label - {{ query.text[:30] }}</title>
    <style>
        body { font-family: system-ui, sans-serif; max-width: 1200px; margin: 40px auto; padding: 0 20px; }
        .query-section { background: #f3f4f6; padding: 20px; border-radius: 8px; margin-bottom: 24px; }
        .query-text { font-size: 18px; font-weight: 500; }
        .query-meta { color: #6b7280; margin-top: 8px; }
        .doc-grid { display: grid; gap: 16px; }
        .doc-card { border: 1px solid #ddd; border-radius: 8px; padding: 16px; }
        .doc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .doc-id { font-weight: bold; color: #374151; }
        .doc-text { background: #f9fafb; padding: 12px; border-radius: 4px; font-family: monospace; font-size: 14px; max-height: 200px; overflow-y: auto; }
        .label-buttons { display: flex; gap: 8px; margin-top: 12px; }
        .btn { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-weight: 500; }
        .btn-relevant { background: #10b981; color: white; }
        .btn-irrelevant { background: #ef4444; color: white; }
        .btn-submit { background: #2563eb; color: white; padding: 12px 24px; font-size: 16px; margin-top: 24px; }
        .selected-relevant { border: 2px solid #10b981; }
        .selected-irrelevant { border: 2px solid #ef4444; }
    </style>
</head>
<body>
    <div class="query-section">
        <div class="query-text">{{ query.text }}</div>
        <div class="query-meta">
            Category: {{ query.category }} |
            Progress: {{ progress.percent }}% ({{ progress.labeled }}/{{ progress.total }})
        </div>
    </div>
    <div class="doc-grid" id="docGrid">
        {% for pair in doc_pairs %}
        <div class="doc-card" data-doc-id="{{ pair.doc_id }}">
            <div class="doc-header">
                <span class="doc-id">Document #{{ pair.doc_id }}</span>
            </div>
            <div class="doc-text">{{ pair.doc_text }}</div>
            <div class="label-buttons">
                <button class="btn btn-irrelevant" onclick="selectLabel({{ pair.doc_id }}, false)">Not Relevant</button>
                <button class="btn btn-relevant" onclick="selectLabel({{ pair.doc_id }}, true)">Relevant</button>
            </div>
        </div>
        {% endfor %}
    </div>
    <button class="btn btn-submit" onclick="submitLabels()">Submit Labels</button>
    <script>
        const labels = {};
        function selectLabel(docId, isRelevant) {
            labels[docId] = isRelevant;
            const card = document.querySelector(`[data-doc-id="${docId}"]`);
            card.classList.remove('selected-relevant', 'selected-irrelevant');
            card.classList.add(isRelevant ? 'selected-relevant' : 'selected-irrelevant');
        }
        function submitLabels() {
            const labelsArray = Object.entries(labels).map(([docId, isRelevant]) => ({
                query_id: '{{ query.id }}',
                doc_id: parseInt(docId),
                is_relevant: isRelevant
            }));
            fetch('/api/label', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ evaluator_id: '{{ evaluator_id }}', labels: labelsArray })
            }).then(r => r.json()).then(data => {
                if (data.success) {
                    alert(`Saved ${data.labeled_count} labels!`);
                    window.location.href = '/evaluator/{{ evaluator_id }}';
                }
            });
        }
    </script>
</body>
</html>'''

        with open(f'{template_dir}/index.html', 'w') as f:
            f.write(index_html)
        with open(f'{template_dir}/dashboard.html', 'w') as f:
            f.write(dashboard_html)
        with open(f'{template_dir}/label.html', 'w') as f:
            f.write(label_html)
