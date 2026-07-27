from typing import List, Dict
import math
from sorts.core.interfaces import IRecommendationEngine
from sorts.core.domain.entities import Club, RecommendationEvidence, TraitMatchEvidence

class DeterministicRecommendationEngine(IRecommendationEngine):
    def __init__(self, trait_names: Dict[str, str] = None):
        """
        Args:
            trait_names: Optional dictionary mapping trait slugs to human-readable names.
        """
        self.trait_names = trait_names or {}

    def _cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """Calculates cosine similarity between two vectors."""
        epsilon = 1e-9
        
        v1_sum_sq = sum(val ** 2 for val in vec1.values())
        v1_norm = math.sqrt(v1_sum_sq)
        
        v2_sum_sq = sum(val ** 2 for val in vec2.values())
        v2_norm = math.sqrt(v2_sum_sq)
        
        if v1_norm <= 0.001 or v2_norm <= 0.001:
            return 0.0
            
        dot_product = sum(vec1.get(k, 0.0) * vec2.get(k, 0.0) for k in vec1.keys())
        return dot_product / (v1_norm * v2_norm + epsilon)

    def calculate_recommendations(
        self, session_traits: Dict[str, float], clubs: List[Club]
    ) -> List[RecommendationEvidence]:
        """Calculates match scores dynamically by separating interests, commitment, and disinterest penalties.
        
        - Positive interest alignment uses non-negative student vector matching.
        - Disinterest (negative student trait values) applies a targeted linear penalty.
        - Official status & verification confidence act as bounded tie-breakers.
        """
        # Classify traits dynamically
        interest_slugs = {slug for slug in session_traits.keys() if "commitment" not in slug}
        commitment_slugs = {slug for slug in session_traits.keys() if "commitment" in slug}

        # Extract student positive & negative vectors
        s_pos_interests = {slug: val for slug, val in session_traits.items() if slug in interest_slugs and val > 0.001}
        s_neg_interests = {slug: abs(val) for slug, val in session_traits.items() if slug in interest_slugs and val < -0.001}
        s_commitments = {slug: val for slug, val in session_traits.items() if slug in commitment_slugs and abs(val) > 0.001}

        results = []

        for club in clubs:
            # Extract club vectors
            c_interests = {}
            c_commitments = {}
            matches = []

            for ct in club.traits:
                if ct.trait_slug in interest_slugs:
                    c_interests[ct.trait_slug] = ct.weight
                elif ct.trait_slug in commitment_slugs:
                    c_commitments[ct.trait_slug] = ct.weight

                s_val = session_traits.get(ct.trait_slug, 0.0)
                contribution = s_val * ct.weight
                if abs(contribution) > 0.001:
                    trait_name = self.trait_names.get(ct.trait_slug, ct.trait_slug.replace("_", " ").title())
                    matches.append(
                        TraitMatchEvidence(
                            trait_slug=ct.trait_slug,
                            trait_name=trait_name,
                            student_weight=s_val,
                            club_weight=ct.weight,
                            contribution=contribution,
                        )
                    )

            # 1. Positive interest cosine similarity (unaffected by negative preferences)
            interest_score = self._cosine_similarity(s_pos_interests, c_interests)
            
            # 2. Commitment cosine similarity
            commitment_score = self._cosine_similarity(s_commitments, c_commitments)

            # 3. Disinterest penalty (if student dis-likes a topic that club specializes in)
            disinterest_penalty = 0.0
            if s_neg_interests and c_interests:
                disinterest_sum = sum(s_neg_interests[slug] * c_interests.get(slug, 0.0) for slug in s_neg_interests)
                c_norm = math.sqrt(sum(v**2 for v in c_interests.values())) + 1e-9
                disinterest_penalty = disinterest_sum / c_norm

            # Combine scores: 85% interest, 15% commitment - 10% disinterest penalty
            if c_interests and interest_score <= 0.0:
                overall_score = 0.0
            else:
                overall_score = (0.85 * interest_score) + (0.15 * commitment_score) - (0.10 * disinterest_penalty)

            # Micro tie-breaker for official status & verification confidence (+0.02 max)
            ver_conf = 1.0
            if hasattr(club, "verification") and isinstance(club.verification, dict):
                ver_conf = club.verification.get("confidence", 100) / 100.0
            official_bonus = 0.015 if getattr(club, "official", False) else 0.005
            overall_score += (official_bonus * ver_conf)

            # Clamp score to [0.0, 1.0] range
            overall_score = max(0.0, min(1.0, overall_score))

            matches.sort(key=lambda m: m.contribution, reverse=True)

            results.append(
                RecommendationEvidence(
                    club_id=club.id if club.id else 0,
                    club_name=club.name,
                    overall_score=overall_score,
                    matches=matches,
                )
            )

        results.sort(key=lambda r: r.overall_score, reverse=True)
        return results
