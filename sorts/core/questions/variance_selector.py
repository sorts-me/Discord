import math
from typing import List, Dict, Optional
from sorts.core.interfaces import IQuestionSelector
from sorts.core.domain.entities import Question, Club

class VarianceQuestionSelector(IQuestionSelector):
    def __init__(self, top_k_cutoff: int = 10, temperature: float = 5.0):
        """
        Args:
            top_k_cutoff: Number of top clubs to consider.
            temperature: Softmax temperature parameter to adjust distribution sharpness.
        """
        self.top_k_cutoff = top_k_cutoff
        self.temperature = temperature

    def _cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """Calculates cosine similarity between two vectors."""
        v1_sum_sq = sum(val ** 2 for val in vec1.values())
        v1_norm = math.sqrt(v1_sum_sq)
        v2_sum_sq = sum(val ** 2 for val in vec2.values())
        v2_norm = math.sqrt(v2_sum_sq)
        if v1_norm <= 0.001 or v2_norm <= 0.001:
            return 0.0
        dot_product = sum(vec1.get(k, 0.0) * vec2.get(k, 0.0) for k in vec1.keys())
        return dot_product / (v1_norm * v2_norm + 1e-9)

    def _calculate_scores(self, traits: Dict[str, float], clubs: List[Club]) -> List[float]:
        """Calculates match scores dynamically by separating interests, commitment, and disinterest penalties."""
        interest_slugs = {slug for slug in traits.keys() if "commitment" not in slug}
        commitment_slugs = {slug for slug in traits.keys() if "commitment" in slug}

        s_pos_interests = {slug: val for slug, val in traits.items() if slug in interest_slugs and val > 0.001}
        s_neg_interests = {slug: abs(val) for slug, val in traits.items() if slug in interest_slugs and val < -0.001}
        s_commitments = {slug: val for slug, val in traits.items() if slug in commitment_slugs and abs(val) > 0.001}

        scores = []
        for club in clubs:
            c_interests = {}
            c_commitments = {}
            for ct in club.traits:
                if ct.trait_slug in interest_slugs:
                    c_interests[ct.trait_slug] = ct.weight
                elif ct.trait_slug in commitment_slugs:
                    c_commitments[ct.trait_slug] = ct.weight

            interest_score = self._cosine_similarity(s_pos_interests, c_interests)
            commitment_score = self._cosine_similarity(s_commitments, c_commitments)

            disinterest_penalty = 0.0
            if s_neg_interests and c_interests:
                disinterest_sum = sum(s_neg_interests[slug] * c_interests.get(slug, 0.0) for slug in s_neg_interests)
                c_norm = math.sqrt(sum(v**2 for v in c_interests.values())) + 1e-9
                disinterest_penalty = disinterest_sum / c_norm

            if c_interests and interest_score <= 0.0:
                overall_score = 0.0
            else:
                overall_score = (0.85 * interest_score) + (0.15 * commitment_score) - (0.10 * disinterest_penalty)

            ver_conf = 1.0
            if hasattr(club, "verification") and isinstance(club.verification, dict):
                ver_conf = club.verification.get("confidence", 100) / 100.0
            official_bonus = 0.015 if getattr(club, "official", False) else 0.005
            overall_score += (official_bonus * ver_conf)

            scores.append(max(0.0, min(1.0, overall_score)))
        return scores

    def _calculate_entropy(self, scores: List[float]) -> float:
        """Applies softmax to scores and calculates Shannon Entropy."""
        if not scores:
            return 0.0
            
        max_score = max(scores)
        exp_scores = [math.exp(self.temperature * (s - max_score)) for s in scores]
        sum_exp = sum(exp_scores)
        
        probabilities = [e / (sum_exp + 1e-9) for e in exp_scores]
        
        entropy = 0.0
        for p in probabilities:
            if p > 1e-6:
                entropy -= p * math.log2(p)
        return entropy

    def select_next_question(
        self, unasked_questions: List[Question], current_session_traits: Dict[str, float], candidate_clubs: List[Club]
    ) -> Optional[Question]:
        """Selects the next question utilizing Shannon Entropy Information Gain.
        It chooses the question that minimizes expected conditional entropy of the candidate matches.
        """
        if not unasked_questions:
            return None
        if not candidate_clubs:
            return unasked_questions[0]

        best_question = None
        best_expected_entropy = float("inf")

        for q in unasked_questions:
            expected_entropy = 0.0
            
            for opt in q.options:
                sim_traits = current_session_traits.copy()
                for mod in opt.trait_modifiers:
                    sim_traits[mod.trait_slug] = max(-1.0, min(1.0, sim_traits.get(mod.trait_slug, 0.0) + mod.weight))
                
                sim_scores = self._calculate_scores(sim_traits, candidate_clubs)
                
                sim_scores.sort(reverse=True)
                top_sim_scores = sim_scores[:self.top_k_cutoff]
                
                expected_entropy += self._calculate_entropy(top_sim_scores)
                
            avg_expected_entropy = expected_entropy / len(q.options) if q.options else 0.0
            
            if avg_expected_entropy < best_expected_entropy:
                best_expected_entropy = avg_expected_entropy
                best_question = q

        return best_question if best_question else unasked_questions[0]
