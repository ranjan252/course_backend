"""
Curriculum DAG engine.

Loads curriculum.json, traverses the topic→subtopic→concept graph,
checks prerequisites, determines what's next for a student.

Curriculum structure:
{
  "topic_id": {
    "display_name": "...",
    "order": 1,
    "prerequisites": ["other_topic_id"],
    "subtopics": {
      "subtopic_id": {
        "display_name": "...",
        "order": 1,
        "prerequisites": ["other_subtopic_id"],
        "concepts": {
          "concept_id": {
            "display_name": "...",
            "level": "L0_L1",
            ...
          }
        }
      }
    }
  }
}
"""
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


class Curriculum:
    """Wraps a curriculum dict with DAG traversal methods."""

    def __init__(self, data: dict):
        self._data = data
        self._concept_index = {}  # concept_id → (topic_id, subtopic_id, concept_data)
        self._build_index()

    def _build_index(self):
        """Build flat lookup: concept_id → location in graph."""
        for topic_id, topic in self._data.items():
            for sub_id, sub in topic.get("subtopics", {}).items():
                for con_id, con in sub.get("concepts", {}).items():
                    self._concept_index[con_id] = (topic_id, sub_id, con)

    # ─── Lookups ─────────────────────────────────

    def get_concept(self, concept_id: str) -> dict | None:
        """Get concept data by ID."""
        entry = self._concept_index.get(concept_id)
        return entry[2] if entry else None

    def get_concept_location(self, concept_id: str) -> tuple | None:
        """Get (topic_id, subtopic_id) for a concept."""
        entry = self._concept_index.get(concept_id)
        return (entry[0], entry[1]) if entry else None

    def get_topic(self, topic_id: str) -> dict | None:
        return self._data.get(topic_id)

    def get_subtopic(self, topic_id: str, subtopic_id: str) -> dict | None:
        topic = self._data.get(topic_id)
        if topic:
            return topic.get("subtopics", {}).get(subtopic_id)
        return None

    def all_concept_ids(self) -> list[str]:
        """All concept IDs in curriculum order."""
        result = []
        for topic_id in self._sorted_topics():
            topic = self._data[topic_id]
            for sub_id in self._sorted_subtopics(topic):
                sub = topic["subtopics"][sub_id]
                for con_id in sub.get("concepts", {}):
                    result.append(con_id)
        return result

    # ─── Ordering ────────────────────────────────

    def _sorted_topics(self) -> list[str]:
        """Topic IDs sorted by order field."""
        return sorted(
            self._data.keys(),
            key=lambda t: self._data[t].get("order", 999)
        )

    def _sorted_subtopics(self, topic: dict) -> list[str]:
        """Subtopic IDs sorted by order field."""
        subs = topic.get("subtopics", {})
        return sorted(subs.keys(), key=lambda s: subs[s].get("order", 999))

    def _sorted_concepts(self, subtopic: dict) -> list[str]:
        """Concept IDs in definition order (dict order, which is insertion order in Python 3.7+)."""
        return list(subtopic.get("concepts", {}).keys())

    # ─── Prerequisite Checking ───────────────────

    def topic_prerequisites_met(self, topic_id: str, completed_concepts: set) -> bool:
        """Check if all prerequisite topics are completed."""
        topic = self._data.get(topic_id)
        if not topic:
            return False

        for prereq_topic_id in topic.get("prerequisites", []):
            prereq_topic = self._data.get(prereq_topic_id)
            if not prereq_topic:
                continue
            # All concepts in prerequisite topic must be completed
            for sub_id, sub in prereq_topic.get("subtopics", {}).items():
                for con_id in sub.get("concepts", {}):
                    if con_id not in completed_concepts:
                        return False
        return True

    def subtopic_prerequisites_met(self, topic_id: str, subtopic_id: str,
                                    completed_concepts: set) -> bool:
        """Check if prerequisite subtopics within the same topic are completed."""
        topic = self._data.get(topic_id)
        if not topic:
            return False
        subtopic = topic.get("subtopics", {}).get(subtopic_id)
        if not subtopic:
            return False

        for prereq_sub_id in subtopic.get("prerequisites", []):
            prereq_sub = topic.get("subtopics", {}).get(prereq_sub_id)
            if not prereq_sub:
                continue
            for con_id in prereq_sub.get("concepts", {}):
                if con_id not in completed_concepts:
                    return False
        return True

    def concept_unlocked(self, concept_id: str, completed_concepts: set) -> bool:
        """Check if a specific concept is unlocked (all prerequisites met)."""
        loc = self.get_concept_location(concept_id)
        if not loc:
            return False
        topic_id, sub_id = loc

        if not self.topic_prerequisites_met(topic_id, completed_concepts):
            return False
        if not self.subtopic_prerequisites_met(topic_id, sub_id, completed_concepts):
            return False
        return True

    # ─── Next Concept Resolution ─────────────────

    def next_concept(self, completed_concepts: set, starting_level: str = None) -> str | None:
        """
        Determine the next concept for a student.

        Walk the DAG in order. Return the first concept that:
        1. Is not yet completed
        2. Has all prerequisites met
        3. Matches or is below the student's level (if starting_level set)

        Returns concept_id or None if course is complete.
        """
        for topic_id in self._sorted_topics():
            topic = self._data[topic_id]

            # Skip topic if prerequisites not met
            if not self.topic_prerequisites_met(topic_id, completed_concepts):
                continue

            for sub_id in self._sorted_subtopics(topic):
                sub = topic["subtopics"][sub_id]

                # Skip subtopic if prerequisites not met
                if not self.subtopic_prerequisites_met(topic_id, sub_id, completed_concepts):
                    continue

                for con_id in self._sorted_concepts(sub):
                    if con_id in completed_concepts:
                        continue

                    # Optionally filter by level
                    if starting_level:
                        con_level = sub["concepts"][con_id].get("level", "L0_L1")
                        if not self._level_accessible(con_level, starting_level):
                            continue

                    return con_id

        return None  # Course complete

    def _level_accessible(self, concept_level: str, student_level: str) -> bool:
        """
        Check if a concept level is accessible to a student.
        For now, all levels are accessible — the level is informational
        for pacing, not a hard gate. Warmup determines starting position,
        not a ceiling.
        """
        # Phase 0: no level gating. Student can access any level.
        # Future: use level to skip L0_L1 for students who tested into L1_L2.
        return True

    # ─── Path Estimation ─────────────────────────

    def estimate_path(self, completed_concepts: set) -> dict:
        """
        Calculate path + time estimate for the student.

        Returns:
        {
            "total_concepts": int,
            "completed": int,
            "remaining": int,
            "estimated_minutes": int,
            "topics": [{ topic_id, display_name, total, completed, status }]
        }
        """
        total = 0
        completed_count = 0
        remaining_minutes = 0
        topics = []

        for topic_id in self._sorted_topics():
            topic = self._data[topic_id]
            t_total = 0
            t_done = 0

            for sub_id, sub in topic.get("subtopics", {}).items():
                for con_id, con in sub.get("concepts", {}).items():
                    t_total += 1
                    total += 1
                    if con_id in completed_concepts:
                        t_done += 1
                        completed_count += 1
                    else:
                        # Use middle of duration_range for estimate
                        dur = con.get("duration_range", [300, 600])
                        remaining_minutes += (dur[0] + dur[1]) / 2 / 60

            if t_done == t_total and t_total > 0:
                status = "completed"
            elif t_done > 0:
                status = "in_progress"
            elif self.topic_prerequisites_met(topic_id, completed_concepts):
                status = "unlocked"
            else:
                status = "locked"

            topics.append({
                "topic_id": topic_id,
                "display_name": topic.get("display_name", topic_id),
                "total": t_total,
                "completed": t_done,
                "status": status,
            })

        return {
            "total_concepts": total,
            "completed": completed_count,
            "remaining": total - completed_count,
            "estimated_minutes": round(remaining_minutes),
            "topics": topics,
        }

    # ─── Foundation Detection ────────────────────

    def is_first_concept_in_subtopic(self, concept_id: str) -> bool:
        """Check if this concept is the first in its subtopic (needs foundation)."""
        loc = self.get_concept_location(concept_id)
        if not loc:
            return False
        topic_id, sub_id = loc
        sub = self._data[topic_id]["subtopics"][sub_id]
        first_con = self._sorted_concepts(sub)[0]
        return concept_id == first_con

    def get_subtopic_id_for_concept(self, concept_id: str) -> str | None:
        """Get the subtopic ID that contains this concept."""
        loc = self.get_concept_location(concept_id)
        return loc[1] if loc else None