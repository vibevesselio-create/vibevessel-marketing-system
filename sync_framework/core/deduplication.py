#!/usr/bin/env python3
"""
Modular Deduplication Engine
=============================

Extracts and generalizes deduplication logic for reuse across all workflows.
Parameterized by item-type to determine matching strategy.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass
import logging

try:
    from rapidfuzz import fuzz, process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False

from sync_framework.core.fingerprinting import FingerprintEngine, FileFingerprint, get_fingerprint_engine

logger = logging.getLogger(__name__)


@dataclass
class DuplicateMatch:
    """Represents a potential duplicate match."""
    item_id: str
    source: str  # 'notion', 'eagle', 'file', etc.
    similarity_score: float
    match_type: str  # 'exact', 'fingerprint', 'fuzzy', 'metadata'
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class DeduplicationEngine:
    """Generic deduplication engine parameterized by item-type."""
    
    def __init__(
        self,
        item_type: str,
        item_type_config: Dict[str, Any]
    ):
        """
        Initialize deduplication engine with item-type-specific configuration.
        
        Args:
            item_type: Name of the item type
            item_type_config: Full item-type configuration from item-types database
        """
        self.item_type = item_type
        self.item_type_config = item_type_config
        self.fingerprint_engine = get_fingerprint_engine()
        
        # Determine matching strategy from item-type config
        self.matching_strategy = self._determine_matching_strategy()
        
        # Thresholds from config or defaults
        validation_rules = item_type_config.get("validation_rules", {})
        self.fingerprint_threshold = validation_rules.get("fingerprint_threshold", 0.95)
        self.fuzzy_threshold = validation_rules.get("fuzzy_threshold", 0.85)
        self.metadata_threshold = validation_rules.get("metadata_threshold", 0.80)
    
    def _determine_matching_strategy(self) -> str:
        """Determine matching strategy from item-type configuration."""
        item_type_lower = self.item_type.lower()
        
        # Check validation rules for explicit strategy
        validation_rules = self.item_type_config.get("validation_rules", {})
        strategy = validation_rules.get("matching_strategy")
        if strategy:
            return strategy
        
        # Infer from item type
        if any(keyword in item_type_lower for keyword in ['audio', 'music', 'track', 'sound']):
            return "audio_fingerprint"
        elif any(keyword in item_type_lower for keyword in ['image', 'photo', 'picture']):
            return "image_perceptual"
        elif any(keyword in item_type_lower for keyword in ['video', 'movie', 'clip']):
            return "video_hash"
        elif any(keyword in item_type_lower for keyword in ['document', 'doc', 'text']):
            return "content_hash"
        else:
            return "fuzzy_metadata"
    
    def find_duplicates(
        self,
        item: Dict[str, Any],
        existing_items: List[Dict[str, Any]],
        file_path: Optional[Path] = None
    ) -> List[DuplicateMatch]:
        """
        Find duplicates using item-type-specific strategy.
        
        Args:
            item: Item to check for duplicates
            existing_items: List of existing items to check against
            file_path: Optional file path for fingerprint matching
            
        Returns:
            List of DuplicateMatch objects sorted by similarity
        """
        matches = []
        
        # Strategy 1: Exact hash match (if fingerprint available)
        if file_path:
            fingerprint = self.fingerprint_engine.compute_fingerprint(
                file_path, self.item_type
            )
            fingerprint_matches = self._find_fingerprint_matches(
                fingerprint, existing_items, file_path
            )
            matches.extend(fingerprint_matches)
        
        # Strategy 2: Metadata matching (title, name, etc.)
        metadata_matches = self._find_metadata_matches(item, existing_items)
        matches.extend(metadata_matches)
        
        # Strategy 3: Fuzzy matching (if enabled)
        if self.matching_strategy in ["fuzzy_metadata", "audio_fingerprint"]:
            fuzzy_matches = self._find_fuzzy_matches(item, existing_items)
            matches.extend(fuzzy_matches)
        
        # Remove duplicates and sort by similarity
        unique_matches = self._deduplicate_matches(matches)
        unique_matches.sort(key=lambda m: m.similarity_score, reverse=True)
        
        return unique_matches
    
    def _find_fingerprint_matches(
        self,
        fingerprint: FileFingerprint,
        existing_items: List[Dict[str, Any]],
        file_path: Path
    ) -> List[DuplicateMatch]:
        """Find matches using fingerprint comparison."""
        matches = []
        
        for existing in existing_items:
            # Check if existing item has fingerprint
            existing_fp_hash = existing.get("fingerprint") or existing.get("fingerprint_hash")
            if existing_fp_hash:
                if existing_fp_hash == fingerprint.hash:
                    matches.append(DuplicateMatch(
                        item_id=existing.get("id") or existing.get("page_id", ""),
                        source=existing.get("source", "unknown"),
                        similarity_score=1.0,
                        match_type="fingerprint",
                        metadata={"fingerprint_hash": existing_fp_hash}
                    ))
                    continue
            
            # Try to compute fingerprint for existing item if path available
            existing_path = existing.get("file_path") or existing.get("path")
            if existing_path:
                try:
                    existing_fp = self.fingerprint_engine.compute_fingerprint(
                        Path(existing_path), self.item_type
                    )
                    similarity = self.fingerprint_engine.compare_fingerprints(
                        fingerprint, existing_fp
                    )
                    if similarity >= self.fingerprint_threshold:
                        matches.append(DuplicateMatch(
                            item_id=existing.get("id") or existing.get("page_id", ""),
                            source=existing.get("source", "unknown"),
                            similarity_score=similarity,
                            match_type="fingerprint",
                            metadata={"computed_similarity": similarity}
                        ))
                except Exception as e:
                    logger.debug(f"Failed to compute fingerprint for {existing_path}: {e}")
        
        return matches
    
    def _find_metadata_matches(
        self,
        item: Dict[str, Any],
        existing_items: List[Dict[str, Any]]
    ) -> List[DuplicateMatch]:
        """Find matches using metadata comparison."""
        matches = []
        
        # Get key fields for matching (from item-type config or defaults)
        key_fields = self.item_type_config.get("validation_rules", {}).get(
            "key_fields", ["title", "name"]
        )
        
        item_values = {}
        for field in key_fields:
            value = item.get(field) or item.get(field.replace("_", "-"))
            if value:
                item_values[field] = str(value).lower().strip()
        
        if not item_values:
            return matches
        
        for existing in existing_items:
            existing_values = {}
            for field in key_fields:
                value = existing.get(field) or existing.get(field.replace("_", "-"))
                if value:
                    existing_values[field] = str(value).lower().strip()
            
            if not existing_values:
                continue
            
            # Calculate similarity
            similarity = self._calculate_metadata_similarity(
                item_values, existing_values, key_fields
            )
            
            if similarity >= self.metadata_threshold:
                matches.append(DuplicateMatch(
                    item_id=existing.get("id") or existing.get("page_id", ""),
                    source=existing.get("source", "unknown"),
                    similarity_score=similarity,
                    match_type="metadata",
                    metadata={"matched_fields": list(existing_values.keys())}
                ))
        
        return matches
    
    def _find_fuzzy_matches(
        self,
        item: Dict[str, Any],
        existing_items: List[Dict[str, Any]]
    ) -> List[DuplicateMatch]:
        """Find matches using fuzzy string matching."""
        if not RAPIDFUZZ_AVAILABLE:
            return []
        
        matches = []
        
        # Get primary field for fuzzy matching
        primary_field = self.item_type_config.get("validation_rules", {}).get(
            "primary_field", "title"
        )
        
        item_value = item.get(primary_field) or item.get(primary_field.replace("_", "-"))
        if not item_value:
            return matches
        
        item_str = str(item_value).lower().strip()
        
        for existing in existing_items:
            existing_value = existing.get(primary_field) or existing.get(primary_field.replace("_", "-"))
            if not existing_value:
                continue
            
            existing_str = str(existing_value).lower().strip()
            
            # Calculate fuzzy similarity
            similarity = fuzz.ratio(item_str, existing_str) / 100.0
            
            if similarity >= self.fuzzy_threshold:
                matches.append(DuplicateMatch(
                    item_id=existing.get("id") or existing.get("page_id", ""),
                    source=existing.get("source", "unknown"),
                    similarity_score=similarity,
                    match_type="fuzzy",
                    metadata={"primary_field": primary_field}
                ))
        
        return matches
    
    def _calculate_metadata_similarity(
        self,
        item_values: Dict[str, str],
        existing_values: Dict[str, str],
        key_fields: List[str]
    ) -> float:
        """Calculate similarity between two metadata dictionaries."""
        if not item_values or not existing_values:
            return 0.0
        
        scores = []
        weights = []
        
        for field in key_fields:
            item_val = item_values.get(field, "")
            existing_val = existing_values.get(field, "")
            
            if not item_val or not existing_val:
                continue
            
            # Exact match
            if item_val == existing_val:
                scores.append(1.0)
                weights.append(1.0)
            else:
                # Fuzzy match if available
                if RAPIDFUZZ_AVAILABLE:
                    similarity = fuzz.ratio(item_val, existing_val) / 100.0
                else:
                    # Simple character-based similarity
                    common = set(item_val) & set(existing_val)
                    total = set(item_val) | set(existing_val)
                    similarity = len(common) / len(total) if total else 0.0
                
                scores.append(similarity)
                weights.append(1.0)
        
        if not scores:
            return 0.0
        
        # Weighted average
        total_weight = sum(weights)
        if total_weight == 0:
            return 0.0
        
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        return weighted_sum / total_weight
    
    def _deduplicate_matches(self, matches: List[DuplicateMatch]) -> List[DuplicateMatch]:
        """Remove duplicate matches (same item_id)."""
        seen = set()
        unique = []
        
        for match in matches:
            key = (match.item_id, match.source)
            if key not in seen:
                seen.add(key)
                unique.append(match)
            else:
                # Keep the one with higher similarity
                existing = next(m for m in unique if (m.item_id, m.source) == key)
                if match.similarity_score > existing.similarity_score:
                    unique.remove(existing)
                    unique.append(match)
        
        return unique
    
    def merge_duplicates(
        self,
        items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Merge duplicate items preserving all metadata.
        
        Args:
            items: List of duplicate items to merge
            
        Returns:
            Merged item dictionary
        """
        if not items:
            return {}
        
        if len(items) == 1:
            return items[0]
        
        # Start with the first item
        merged = items[0].copy()
        
        # Merge metadata from all items
        for item in items[1:]:
            # Merge tags/labels
            merged_tags = set(merged.get("tags", []) or [])
            item_tags = set(item.get("tags", []) or [])
            merged["tags"] = sorted(list(merged_tags | item_tags))
            
            # Merge other list fields
            for field in ["labels", "categories", "relations"]:
                merged_list = set(merged.get(field, []) or [])
                item_list = set(item.get(field, []) or [])
                if merged_list or item_list:
                    merged[field] = sorted(list(merged_list | item_list))
            
            # Keep non-empty values for other fields
            for key, value in item.items():
                if key not in merged or not merged[key]:
                    if value:
                        merged[key] = value
        
        return merged
    
    def is_duplicate(
        self,
        item: Dict[str, Any],
        existing_items: List[Dict[str, Any]],
        file_path: Optional[Path] = None
    ) -> Tuple[bool, Optional[DuplicateMatch]]:
        """
        Check if item is a duplicate.
        
        Args:
            item: Item to check
            existing_items: Existing items to check against
            file_path: Optional file path for fingerprinting
            
        Returns:
            Tuple of (is_duplicate, best_match)
        """
        matches = self.find_duplicates(item, existing_items, file_path)
        
        if not matches:
            return False, None
        
        best_match = matches[0]
        
        # Determine if it's a duplicate based on match type and threshold
        is_dup = False
        if best_match.match_type == "fingerprint":
            is_dup = best_match.similarity_score >= self.fingerprint_threshold
        elif best_match.match_type == "metadata":
            is_dup = best_match.similarity_score >= self.metadata_threshold
        elif best_match.match_type == "fuzzy":
            is_dup = best_match.similarity_score >= self.fuzzy_threshold
        
        return is_dup, best_match if is_dup else None
