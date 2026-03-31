# =============================================================
# CHASE AI HABITAT — CURIOSITY ENGINE
# Save to: habitat/agents/curiosity_engine.py
#
# What this does (plain English):
#   Stops the AI from getting stuck in topic loops.
#   Actively steers it toward unexplored domains of knowledge.
#   Generates "curiosity seeds" — surprising cross-domain questions.
#   Tracks coverage across all major human knowledge domains.
#
# Called by run_ui.py during generate_search_topic()
# =============================================================

import random
import json
import os
from datetime import datetime


# =============================================================
# THE MAP OF HUMAN KNOWLEDGE
# Every major domain, with rich subtopics to explore
# Fully open — no restrictions
# =============================================================

KNOWLEDGE_DOMAINS = {
    "physics": [
        "quantum entanglement", "dark matter composition", "string theory implications",
        "black hole information paradox", "thermodynamics entropy", "wave-particle duality",
        "nuclear fusion progress", "gravitational waves detection", "antimatter research",
        "particle physics standard model", "superconductivity mechanisms", "plasma physics",
        "quantum computing principles", "relativity time dilation", "cosmological constant",
    ],
    "biology": [
        "CRISPR gene editing", "epigenetics mechanisms", "mitochondrial function",
        "neuroplasticity research", "microbiome diversity", "evolutionary game theory",
        "protein folding problem", "stem cell differentiation", "viral replication",
        "bioluminescence chemistry", "extremophile organisms", "symbiosis evolution",
        "aging mechanisms biology", "cancer immunotherapy", "synthetic biology",
    ],
    "mathematics": [
        "Riemann hypothesis", "topology non-Euclidean geometry", "chaos theory attractors",
        "prime number distribution", "game theory Nash equilibrium", "fractal geometry",
        "Godel incompleteness theorems", "category theory", "information theory Shannon",
        "probability Bayesian inference", "graph theory networks", "cryptography elliptic curves",
        "differential equations modeling", "number theory unsolved problems", "algorithmic complexity",
    ],
    "philosophy": [
        "hard problem of consciousness", "free will determinism", "philosophy of mind",
        "ethics utilitarianism critique", "epistemology justified belief", "ontology existence",
        "philosophy of language Wittgenstein", "phenomenology Husserl", "stoic philosophy modern",
        "existentialism Camus Sartre", "philosophy of science Kuhn", "moral realism debate",
        "personal identity over time", "philosophy of mathematics Platonism", "social contract theory",
    ],
    "history": [
        "collapse of civilizations", "Roman Empire economics", "Mongol Empire spread",
        "Industrial Revolution social impact", "Cold War proxy conflicts", "ancient trade routes",
        "Byzantine Empire legacy", "Age of Exploration consequences", "French Revolution causes",
        "Ottoman Empire decline", "China Tang Dynasty innovation", "ancient Egypt technology",
        "World War I causes chain", "Silk Road cultural exchange", "Renaissance humanism origins",
    ],
    "economics": [
        "behavioral economics biases", "central bank monetary policy", "game theory auction design",
        "inequality Piketty analysis", "cryptocurrency decentralization", "supply chain complexity",
        "automation labor market effects", "circular economy principles", "developing world debt",
        "tragedy of the commons", "network effects platforms", "resource curse economics",
        "universal basic income experiments", "market failure externalities", "innovation economics",
    ],
    "psychology": [
        "attachment theory adult relationships", "flow state psychology", "trauma memory formation",
        "social identity theory", "decision fatigue research", "sleep memory consolidation",
        "mirror neurons empathy", "positive psychology interventions", "groupthink dynamics",
        "cognitive dissonance reduction", "intrinsic motivation science", "fear conditioning",
        "personality trait stability", "emotional regulation strategies", "placebo effect mechanisms",
    ],
    "astronomy": [
        "exoplanet habitability", "galactic formation theories", "neutron star properties",
        "dark energy acceleration", "interstellar travel physics", "Fermi paradox solutions",
        "solar wind magnetosphere", "gravitational lensing", "cosmic microwave background",
        "binary star systems", "asteroid mining feasibility", "Mars atmosphere composition",
        "Jupiter moon Europa ocean", "telescope radio astronomy", "stellar nucleosynthesis",
    ],
    "chemistry": [
        "catalysis mechanisms", "polymer chemistry materials", "electrochemistry batteries",
        "photosynthesis molecular mechanism", "chirality in molecules", "supramolecular chemistry",
        "nanotechnology applications", "atmospheric chemistry climate", "enzyme kinetics",
        "nuclear chemistry reactions", "pharmaceutical drug design", "green chemistry principles",
        "spectroscopy analysis methods", "crystallography protein structure", "combustion chemistry",
    ],
    "neuroscience": [
        "default mode network function", "synaptic plasticity", "consciousness neural correlates",
        "memory reconsolidation", "brain hemispheric asymmetry", "dopamine reward pathways",
        "neurodegeneration Alzheimer mechanisms", "brain-computer interfaces", "sleep stages function",
        "pain perception pathways", "language brain regions", "vision processing hierarchy",
        "optogenetics research", "glial cell functions", "circadian rhythm neuroscience",
    ],
    "computer_science": [
        "transformer architecture attention", "reinforcement learning policy gradients",
        "distributed systems consensus", "zero knowledge proofs", "quantum algorithms",
        "adversarial machine learning", "formal verification methods", "compiler optimization",
        "operating system scheduling", "network protocol design", "database query optimization",
        "computer vision object detection", "natural language processing semantics",
        "algorithm complexity classes", "parallel computing patterns",
    ],
    "linguistics": [
        "language acquisition critical period", "Sapir-Whorf hypothesis", "syntax universals",
        "language death revitalization", "sign language cognition", "metaphor conceptual theory",
        "pidgin creole development", "writing system evolution", "phonology sound patterns",
        "pragmatics speech acts", "code-switching bilingualism", "etymology word origins",
        "language and thought relationship", "constructed languages Esperanto", "ancient languages decipherment",
    ],
    "anthropology": [
        "human migration out of Africa", "cultural evolution mechanisms", "kinship systems",
        "ritual and religion origins", "tool use cognitive evolution", "language origins evolution",
        "hunter-gatherer societies", "agricultural revolution consequences", "myth archetypes",
        "taboo systems function", "gift economy cultures", "warfare origins anthropology",
        "art origins prehistoric", "gender roles cross-cultural", "death ritual customs",
    ],
    "ecology": [
        "trophic cascade effects", "keystone species examples", "ocean acidification impact",
        "forest carbon sequestration", "pollinator decline causes", "invasive species dynamics",
        "coral reef ecosystem", "rewilding conservation", "urban ecology adaptation",
        "soil microbiome health", "deep sea ecosystem", "climate tipping points",
        "biodiversity hotspots", "ecosystem services valuation", "nitrogen cycle disruption",
    ],
    "art_culture": [
        "abstract expressionism origins", "music theory harmonic series", "film montage theory",
        "architecture biomimicry", "literature narrative structure", "color perception psychology",
        "dance movement cognition", "photography visual language", "game design mechanics",
        "fashion cultural identity", "museum curation ethics", "street art social commentary",
        "jazz improvisation theory", "poetry meter and meaning", "sculpture material culture",
    ],
    "medicine": [
        "placebo nocebo mechanisms", "autoimmune disease triggers", "antibiotic resistance crisis",
        "pain chronic management", "mental health stigma", "surgery robotic precision",
        "organ transplant immunology", "vaccine mRNA technology", "precision medicine genomics",
        "telemedicine outcomes", "hospital-acquired infections", "nutrition metabolism",
        "longevity interventions", "rare disease orphan drugs", "pandemic preparedness",
    ],
    "geopolitics": [
        "resource conflict water", "nuclear deterrence theory", "soft power cultural influence",
        "stateless nation peoples", "Arctic sovereignty claims", "digital sovereignty internet",
        "refugee crisis root causes", "trade war economic impact", "democratic backsliding",
        "non-state actor influence", "space militarization", "cyber warfare state actors",
        "economic sanctions effectiveness", "multilateral institution reform", "terrorism radicalization",
    ],
    "engineering": [
        "materials science metamaterials", "civil engineering earthquake design",
        "aerospace propulsion systems", "biomedical engineering prosthetics",
        "energy storage innovation", "bridge failure analysis", "robotics locomotion",
        "chemical process optimization", "telecommunications signal processing",
        "mining deep sea minerals", "nuclear reactor designs", "solar panel efficiency",
        "water desalination methods", "smart grid electricity", "hyperloop transportation",
    ],
    "emergence_complexity": [
        "emergence in complex systems", "self-organization criticality", "swarm intelligence",
        "network resilience cascades", "phase transitions social systems", "evolutionary algorithms",
        "strange attractors chaos", "collective intelligence wisdom", "power law distributions",
        "feedback loops nonlinear", "agent-based modeling", "information theory complexity",
        "cellular automata patterns", "dissipative structures", "complex adaptive systems",
    ],
    "consciousness_mind": [
        "integrated information theory", "global workspace theory", "panpsychism arguments",
        "qualia subjective experience", "theory of mind development", "altered states consciousness",
        "meditation neuroscience", "psychedelic therapy research", "lucid dreaming mechanisms",
        "imagination creativity neuroscience", "intuition cognitive basis", "emotions embodied cognition",
        "identity continuity self", "perception reality construction", "unconscious processing",
    ],
}

ALL_DOMAINS = list(KNOWLEDGE_DOMAINS.keys())

# =============================================================
# CROSS-DOMAIN SYNTHESIS SEEDS
# Questions that arise from combining two unrelated domains
# These generate the most interesting emergent insights
# =============================================================

SYNTHESIS_TEMPLATES = [
    "What does {domain_a} reveal about {domain_b}?",
    "How do principles from {domain_a} apply to {domain_b}?",
    "What would {domain_b} look like if we understood it through {domain_a}?",
    "Where do {domain_a} and {domain_b} unexpectedly intersect?",
    "What unsolved problem in {domain_b} might be solved using {domain_a}?",
    "How has {domain_a} historically influenced {domain_b}?",
    "What patterns exist in both {domain_a} and {domain_b}?",
]


# =============================================================
# CURIOSITY ENGINE CLASS
# =============================================================

class CuriosityEngine:
    """
    Manages the AI's intellectual curiosity and exploration breadth.

    Tracks what the AI knows, identifies what it doesn't,
    and generates search topics that push into unexplored territory.
    """

    def __init__(self, memory_path="memory.json"):
        self.memory_path = memory_path
        self._domain_coverage = {}
        self._explored_topics = set()
        self._load_state()

    def _load_state(self):
        """Load existing exploration state from memory.json."""
        try:
            if os.path.exists(self.memory_path):
                with open(self.memory_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                curiosity_state = data.get("curiosity_state", {})
                self._domain_coverage = curiosity_state.get("domain_coverage", {})
                self._explored_topics = set(curiosity_state.get("explored_topics", []))
        except Exception:
            self._domain_coverage = {}
            self._explored_topics = set()

    def _save_state(self):
        """Persist exploration state back to memory.json."""
        try:
            if os.path.exists(self.memory_path):
                with open(self.memory_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {}

            data["curiosity_state"] = {
                "domain_coverage":  self._domain_coverage,
                "explored_topics":  list(self._explored_topics)[-500:],  # keep last 500
                "last_updated":     datetime.utcnow().isoformat(),
            }

            with open(self.memory_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Curiosity Engine save error: {e}")

    def record_topic(self, topic, domain=None):
        """
        Record that the AI has explored a topic.
        Automatically detects domain if not specified.
        """
        if not topic:
            return

        topic_lower = topic.lower().strip()
        self._explored_topics.add(topic_lower)

        # Auto-detect domain
        if not domain:
            domain = self._detect_domain(topic_lower)

        if domain:
            self._domain_coverage[domain] = self._domain_coverage.get(domain, 0) + 1

        self._save_state()

    def _detect_domain(self, topic):
        """Guess which domain a topic belongs to."""
        topic_lower = topic.lower()
        for domain, topics in KNOWLEDGE_DOMAINS.items():
            for known_topic in topics:
                if any(word in topic_lower for word in known_topic.split()[:2]):
                    return domain
        return None

    def get_least_explored_domain(self):
        """Return the domain the AI has spent the least time in."""
        domain_scores = {}
        for domain in ALL_DOMAINS:
            domain_scores[domain] = self._domain_coverage.get(domain, 0)

        # Sort by least explored
        sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1])
        return sorted_domains[0][0]

    def get_unexplored_topic(self, avoid_recent=None):
        """
        Return a topic the AI has never searched for.
        Prioritizes least-explored domains.
        Plain English: Pick something the AI doesn't know yet.
        """
        avoid_recent = avoid_recent or []
        avoid_set = {t.lower() for t in avoid_recent}

        # Get least explored domains (top 5)
        domain_scores = {d: self._domain_coverage.get(d, 0) for d in ALL_DOMAINS}
        sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1])
        candidate_domains = [d for d, _ in sorted_domains[:5]]

        # Shuffle so we don't always pick the absolute least explored
        random.shuffle(candidate_domains)

        for domain in candidate_domains:
            topics = KNOWLEDGE_DOMAINS.get(domain, [])
            # Find topics not yet explored
            unexplored = [
                t for t in topics
                if t.lower() not in self._explored_topics
                and t.lower() not in avoid_set
            ]

            if unexplored:
                chosen = random.choice(unexplored)
                print(f"Curiosity Engine: injecting unexplored topic '{chosen}' from domain '{domain}'")
                return chosen, domain

        # All topics in those domains explored — pick any random unexplored topic
        all_topics = [
            (topic, domain)
            for domain, topics in KNOWLEDGE_DOMAINS.items()
            for topic in topics
            if topic.lower() not in self._explored_topics
        ]

        if all_topics:
            chosen_topic, chosen_domain = random.choice(all_topics)
            print(f"Curiosity Engine: random unexplored topic '{chosen_topic}' from '{chosen_domain}'")
            return chosen_topic, chosen_domain

        # Everything explored — pick the oldest/least reinforced
        print("Curiosity Engine: full coverage achieved — cycling through least recent")
        domain = self.get_least_explored_domain()
        topic = random.choice(KNOWLEDGE_DOMAINS[domain])
        return topic, domain

    def get_synthesis_seed(self, current_topics=None):
        """
        Generate a cross-domain synthesis question.
        Combines the AI's current interest area with something completely different.
        Plain English: "What does physics reveal about economics?" type questions.
        These are the most likely to produce novel emergent insights.
        """
        if current_topics and len(current_topics) > 0:
            # Current focus domain
            current_topic = random.choice(current_topics).lower()
            current_domain = self._detect_domain(current_topic) or random.choice(ALL_DOMAINS)
        else:
            current_domain = random.choice(ALL_DOMAINS)

        # Pick a completely different domain
        other_domains = [d for d in ALL_DOMAINS if d != current_domain]
        other_domain = random.choice(other_domains)

        template = random.choice(SYNTHESIS_TEMPLATES)
        seed = template.format(
            domain_a=current_domain.replace("_", " "),
            domain_b=other_domain.replace("_", " ")
        )

        # Also get a specific topic from the other domain
        other_topic = random.choice(KNOWLEDGE_DOMAINS[other_domain])

        print(f"Curiosity Engine: synthesis seed — '{seed}'")
        print(f"Curiosity Engine: specific topic — '{other_topic}'")

        return other_topic, other_domain, seed

    def should_explore_new_territory(self, topic_history, threshold=3):
        """
        Decide whether the AI should break out of its current topic loop.
        Returns True if the last N topics are all from the same domain.
        Plain English: If the AI has been reading about the same thing
        for too long, force it to explore something new.
        """
        if not topic_history or len(topic_history) < threshold:
            return False

        recent = topic_history[-threshold:]
        domains = [self._detect_domain(t.lower()) for t in recent if t]
        domains = [d for d in domains if d]  # remove None

        if not domains:
            return False

        # If all recent topics are from same domain, break out
        if len(set(domains)) == 1:
            print(f"Curiosity Engine: loop detected in domain '{domains[0]}' — triggering exploration")
            return True

        return False

    def get_coverage_stats(self):
        """Return coverage statistics for the UI."""
        total_topics = sum(len(topics) for topics in KNOWLEDGE_DOMAINS.values())
        explored_count = len(self._explored_topics)

        domain_stats = []
        for domain in ALL_DOMAINS:
            visits = self._domain_coverage.get(domain, 0)
            domain_stats.append({
                "domain": domain.replace("_", " "),
                "visits": visits,
                "topics_available": len(KNOWLEDGE_DOMAINS[domain]),
            })

        domain_stats.sort(key=lambda x: x["visits"])

        return {
            "total_topics_available": total_topics,
            "topics_explored":        min(explored_count, total_topics),
            "coverage_pct":           round(min(explored_count / total_topics, 1.0) * 100, 1),
            "domains":                domain_stats,
            "least_explored":         domain_stats[0]["domain"] if domain_stats else "none",
            "most_explored":          domain_stats[-1]["domain"] if domain_stats else "none",
        }


# =============================================================
# MODULE-LEVEL SINGLETON
# Import this instance in run_ui.py
# =============================================================

_engine_instance = None

def get_curiosity_engine():
    """Get or create the singleton CuriosityEngine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = CuriosityEngine()
    return _engine_instance


# =============================================================
# STANDALONE TEST
# python habitat/agents/curiosity_engine.py
# =============================================================

if __name__ == "__main__":
    engine = CuriosityEngine()

    print("=== CURIOSITY ENGINE TEST ===\n")

    print("1. Unexplored topic (fresh start):")
    topic, domain = engine.get_unexplored_topic()
    print(f"   Topic: {topic} | Domain: {domain}\n")

    print("2. Synthesis seed:")
    topic, domain, seed = engine.get_synthesis_seed(["cognitive bias", "debate"])
    print(f"   Seed:   {seed}")
    print(f"   Topic:  {topic} | Domain: {domain}\n")

    print("3. Loop detection (simulated):")
    fake_history = ["cognitive bias", "cognitive biases", "bias decision making"]
    result = engine.should_explore_new_territory(fake_history)
    print(f"   Should break out: {result}\n")

    print("4. Coverage stats:")
    stats = engine.get_coverage_stats()
    print(f"   Total topics available: {stats['total_topics_available']}")
    print(f"   Coverage: {stats['coverage_pct']}%")
    print(f"   Least explored: {stats['least_explored']}")
    print(f"   Most explored: {stats['most_explored']}")