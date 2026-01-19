"""Library validation and consistency checking.

This module provides validation tools for ensuring consistency
across Apple Music, Rekordbox, djay Pro, and Notion libraries.

Validates:
- Track count consistency
- File path integrity
- Metadata completeness
- Cross-platform ID linkage
- BPM/Key analysis coverage

Example usage:
    from unified_sync.validators import LibraryValidator

    validator = LibraryValidator(matcher)
    report = validator.full_validation()

    print(f"Health Score: {report.health_score}%")
    for issue in report.issues:
        print(f"  - {issue.severity}: {issue.message}")
"""

import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from .cross_matcher import CrossPlatformMatcher, UnifiedTrackMatch

logger = logging.getLogger("unified_sync.validators")


class IssueSeverity(Enum):
    """Severity levels for validation issues."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationIssue:
    """A single validation issue.

    Attributes:
        severity: Issue severity level
        category: Issue category (e.g., "missing_file", "bpm_mismatch")
        message: Human-readable description
        affected_tracks: List of affected track IDs
        platform: Platform where issue was found
        details: Additional details
    """
    severity: IssueSeverity
    category: str
    message: str
    affected_tracks: List[str] = field(default_factory=list)
    platform: Optional[str] = None
    details: Optional[Dict] = None


@dataclass
class ValidationReport:
    """Complete validation report.

    Attributes:
        timestamp: When validation was run
        health_score: Overall health percentage (0-100)
        total_tracks: Total unique tracks across all platforms
        platforms_checked: List of platforms validated
        issues: List of validation issues
        statistics: Platform-specific statistics
    """
    timestamp: datetime = field(default_factory=datetime.now)
    health_score: float = 100.0
    total_tracks: int = 0
    platforms_checked: List[str] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            "=" * 60,
            "LIBRARY VALIDATION REPORT",
            "=" * 60,
            f"Timestamp: {self.timestamp.isoformat()}",
            f"Health Score: {self.health_score:.1f}%",
            f"Total Tracks: {self.total_tracks}",
            f"Platforms: {', '.join(self.platforms_checked)}",
            "",
        ]

        # Group issues by severity
        by_severity = {}
        for issue in self.issues:
            sev = issue.severity.value
            if sev not in by_severity:
                by_severity[sev] = []
            by_severity[sev].append(issue)

        lines.append("ISSUES BY SEVERITY:")
        for severity in ["critical", "error", "warning", "info"]:
            count = len(by_severity.get(severity, []))
            lines.append(f"  {severity.upper()}: {count}")

        if self.issues:
            lines.append("\nTOP ISSUES:")
            shown = 0
            for severity in ["critical", "error", "warning"]:
                for issue in by_severity.get(severity, []):
                    if shown >= 10:
                        break
                    lines.append(
                        f"  [{issue.severity.value.upper()}] {issue.category}: "
                        f"{issue.message}"
                    )
                    shown += 1

        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "health_score": self.health_score,
            "total_tracks": self.total_tracks,
            "platforms_checked": self.platforms_checked,
            "issue_counts": {
                severity.value: len([
                    i for i in self.issues if i.severity == severity
                ])
                for severity in IssueSeverity
            },
            "statistics": self.statistics,
        }


class LibraryValidator:
    """Validate music library consistency across platforms.

    Performs comprehensive validation including:
    - Track count consistency
    - File existence checks
    - Metadata completeness
    - BPM/Key coverage
    - Cross-platform linking

    Attributes:
        matcher: CrossPlatformMatcher with loaded libraries
    """

    # Thresholds for health score calculation
    THRESHOLDS = {
        "count_mismatch_warning": 0.05,  # 5% difference triggers warning
        "count_mismatch_error": 0.15,  # 15% difference triggers error
        "bpm_coverage_warning": 0.80,  # 80% BPM coverage expected
        "key_coverage_warning": 0.70,  # 70% Key coverage expected
        "link_coverage_warning": 0.90,  # 90% cross-platform linking expected
    }

    def __init__(self, matcher: CrossPlatformMatcher):
        """Initialize the validator.

        Args:
            matcher: CrossPlatformMatcher with libraries loaded
        """
        self.matcher = matcher

    def full_validation(self) -> ValidationReport:
        """Run full validation across all loaded libraries.

        Returns:
            ValidationReport with all findings
        """
        logger.info("Running full library validation...")
        report = ValidationReport()

        # Build unified index if not already done
        unified_tracks = self.matcher.build_unified_index()
        report.total_tracks = len(unified_tracks)

        # Determine which platforms are loaded
        if self.matcher._notion_tracks:
            report.platforms_checked.append("notion")
        if self.matcher._apple_music_tracks:
            report.platforms_checked.append("apple_music")
        if self.matcher._rekordbox_tracks:
            report.platforms_checked.append("rekordbox")
        if self.matcher._djay_pro_tracks:
            report.platforms_checked.append("djay_pro")

        # Run validations
        self._validate_track_counts(report)
        self._validate_file_paths(report, unified_tracks)
        self._validate_metadata_completeness(report, unified_tracks)
        self._validate_bpm_coverage(report, unified_tracks)
        self._validate_key_coverage(report, unified_tracks)
        self._validate_cross_platform_links(report, unified_tracks)
        self._validate_conflicts(report, unified_tracks)

        # Calculate health score
        report.health_score = self._calculate_health_score(report)

        # Add statistics
        report.statistics = self.matcher.get_statistics()

        logger.info(f"Validation complete: {report.health_score:.1f}% health score")
        return report

    def _validate_track_counts(self, report: ValidationReport):
        """Validate track count consistency across platforms."""
        counts = {
            "notion": len(self.matcher._notion_tracks),
            "apple_music": len(self.matcher._apple_music_tracks),
            "rekordbox": len(self.matcher._rekordbox_tracks),
            "djay_pro": len(self.matcher._djay_pro_tracks),
        }

        # Filter to only loaded platforms
        active_counts = {k: v for k, v in counts.items() if v > 0}

        if len(active_counts) < 2:
            return  # Need at least 2 platforms to compare

        # Use Notion as reference if available, otherwise largest
        reference_platform = "notion" if counts["notion"] > 0 else max(
            active_counts, key=active_counts.get
        )
        reference_count = active_counts[reference_platform]

        for platform, count in active_counts.items():
            if platform == reference_platform:
                continue

            diff_pct = abs(count - reference_count) / reference_count

            if diff_pct > self.THRESHOLDS["count_mismatch_error"]:
                report.issues.append(ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="track_count_mismatch",
                    message=f"{platform} has {count} tracks vs {reference_platform}'s {reference_count} ({diff_pct*100:.1f}% difference)",
                    platform=platform,
                    details={
                        "platform_count": count,
                        "reference_count": reference_count,
                        "difference_pct": diff_pct,
                    }
                ))
            elif diff_pct > self.THRESHOLDS["count_mismatch_warning"]:
                report.issues.append(ValidationIssue(
                    severity=IssueSeverity.WARNING,
                    category="track_count_mismatch",
                    message=f"{platform} has {diff_pct*100:.1f}% fewer/more tracks than {reference_platform}",
                    platform=platform,
                ))

    def _validate_file_paths(
        self,
        report: ValidationReport,
        unified_tracks: List[UnifiedTrackMatch]
    ):
        """Validate that file paths exist and are consistent."""
        missing_files = []
        path_mismatches = []

        for track in unified_tracks:
            if not track.file_path:
                continue

            # Check if file exists
            path = Path(track.file_path)
            if not path.exists():
                missing_files.append(track.match_id)

            # Check for path consistency across platforms
            paths = set()
            for ref in track.platform_refs.values():
                if ref.file_path:
                    paths.add(ref.file_path.lower())

            if len(paths) > 1:
                path_mismatches.append({
                    "match_id": track.match_id,
                    "paths": list(paths),
                })

        if missing_files:
            report.issues.append(ValidationIssue(
                severity=IssueSeverity.WARNING,
                category="missing_files",
                message=f"{len(missing_files)} tracks reference missing audio files",
                affected_tracks=missing_files[:50],  # Limit for report size
                details={"total_missing": len(missing_files)},
            ))

        if path_mismatches:
            report.issues.append(ValidationIssue(
                severity=IssueSeverity.INFO,
                category="path_mismatch",
                message=f"{len(path_mismatches)} tracks have different paths across platforms",
                details={"examples": path_mismatches[:5]},
            ))

    def _validate_metadata_completeness(
        self,
        report: ValidationReport,
        unified_tracks: List[UnifiedTrackMatch]
    ):
        """Validate metadata completeness."""
        missing_title = 0
        missing_artist = 0
        missing_album = 0

        for track in unified_tracks:
            if not track.canonical_title or track.canonical_title.strip() == "":
                missing_title += 1
            if not track.canonical_artist or track.canonical_artist.strip() == "":
                missing_artist += 1
            if not track.canonical_album or track.canonical_album.strip() == "":
                missing_album += 1

        total = len(unified_tracks)
        if total == 0:
            return

        if missing_title > 0:
            report.issues.append(ValidationIssue(
                severity=IssueSeverity.ERROR if missing_title > total * 0.01 else IssueSeverity.WARNING,
                category="missing_title",
                message=f"{missing_title} tracks ({100*missing_title/total:.1f}%) missing title",
            ))

        if missing_artist > total * 0.05:
            report.issues.append(ValidationIssue(
                severity=IssueSeverity.WARNING,
                category="missing_artist",
                message=f"{missing_artist} tracks ({100*missing_artist/total:.1f}%) missing artist",
            ))

        if missing_album > total * 0.10:
            report.issues.append(ValidationIssue(
                severity=IssueSeverity.INFO,
                category="missing_album",
                message=f"{missing_album} tracks ({100*missing_album/total:.1f}%) missing album",
            ))

    def _validate_bpm_coverage(
        self,
        report: ValidationReport,
        unified_tracks: List[UnifiedTrackMatch]
    ):
        """Validate BPM analysis coverage."""
        with_bpm = sum(1 for t in unified_tracks if t.canonical_bpm and t.canonical_bpm > 0)
        total = len(unified_tracks)

        if total == 0:
            return

        coverage = with_bpm / total

        report.statistics["bpm_coverage"] = f"{coverage*100:.1f}%"

        if coverage < self.THRESHOLDS["bpm_coverage_warning"]:
            report.issues.append(ValidationIssue(
                severity=IssueSeverity.WARNING,
                category="low_bpm_coverage",
                message=f"Only {coverage*100:.1f}% of tracks have BPM analyzed (target: {self.THRESHOLDS['bpm_coverage_warning']*100:.0f}%)",
                details={
                    "with_bpm": with_bpm,
                    "total": total,
                    "coverage": coverage,
                }
            ))

    def _validate_key_coverage(
        self,
        report: ValidationReport,
        unified_tracks: List[UnifiedTrackMatch]
    ):
        """Validate key detection coverage."""
        with_key = sum(1 for t in unified_tracks if t.canonical_key)
        total = len(unified_tracks)

        if total == 0:
            return

        coverage = with_key / total

        report.statistics["key_coverage"] = f"{coverage*100:.1f}%"

        if coverage < self.THRESHOLDS["key_coverage_warning"]:
            report.issues.append(ValidationIssue(
                severity=IssueSeverity.WARNING,
                category="low_key_coverage",
                message=f"Only {coverage*100:.1f}% of tracks have key detected (target: {self.THRESHOLDS['key_coverage_warning']*100:.0f}%)",
                details={
                    "with_key": with_key,
                    "total": total,
                    "coverage": coverage,
                }
            ))

    def _validate_cross_platform_links(
        self,
        report: ValidationReport,
        unified_tracks: List[UnifiedTrackMatch]
    ):
        """Validate cross-platform ID linkage."""
        # Count tracks linked across platforms
        multi_platform = sum(1 for t in unified_tracks if len(t.platforms) > 1)
        all_platforms = sum(1 for t in unified_tracks if len(t.platforms) == 4)
        single_platform = sum(1 for t in unified_tracks if len(t.platforms) == 1)

        total = len(unified_tracks)
        if total == 0:
            return

        link_rate = multi_platform / total

        report.statistics["cross_platform_linked"] = f"{link_rate*100:.1f}%"
        report.statistics["all_platforms_linked"] = all_platforms
        report.statistics["single_platform_only"] = single_platform

        if link_rate < self.THRESHOLDS["link_coverage_warning"]:
            report.issues.append(ValidationIssue(
                severity=IssueSeverity.WARNING,
                category="low_cross_platform_links",
                message=f"Only {link_rate*100:.1f}% of tracks are linked across platforms",
                details={
                    "multi_platform": multi_platform,
                    "single_platform": single_platform,
                    "all_platforms": all_platforms,
                }
            ))

        if single_platform > total * 0.1:
            report.issues.append(ValidationIssue(
                severity=IssueSeverity.INFO,
                category="orphan_tracks",
                message=f"{single_platform} tracks exist in only one platform",
            ))

    def _validate_conflicts(
        self,
        report: ValidationReport,
        unified_tracks: List[UnifiedTrackMatch]
    ):
        """Validate and report conflicts."""
        with_conflicts = [t for t in unified_tracks if t.has_conflicts]

        if not with_conflicts:
            return

        # Categorize conflicts
        bpm_conflicts = sum(
            1 for t in with_conflicts
            for c in t.conflicts if c["field"] == "bpm"
        )
        key_conflicts = sum(
            1 for t in with_conflicts
            for c in t.conflicts if c["field"] == "key"
        )

        report.statistics["tracks_with_conflicts"] = len(with_conflicts)
        report.statistics["bpm_conflicts"] = bpm_conflicts
        report.statistics["key_conflicts"] = key_conflicts

        if bpm_conflicts > 0:
            report.issues.append(ValidationIssue(
                severity=IssueSeverity.WARNING,
                category="bpm_conflict",
                message=f"{bpm_conflicts} tracks have conflicting BPM values across platforms",
                affected_tracks=[t.match_id for t in with_conflicts if any(
                    c["field"] == "bpm" for c in t.conflicts
                )][:20],
            ))

        if key_conflicts > 0:
            report.issues.append(ValidationIssue(
                severity=IssueSeverity.WARNING,
                category="key_conflict",
                message=f"{key_conflicts} tracks have conflicting key values across platforms",
            ))

    def _calculate_health_score(self, report: ValidationReport) -> float:
        """Calculate overall health score (0-100).

        Args:
            report: Report with issues

        Returns:
            Health score percentage
        """
        score = 100.0

        # Deduct points based on issue severity
        for issue in report.issues:
            if issue.severity == IssueSeverity.CRITICAL:
                score -= 25
            elif issue.severity == IssueSeverity.ERROR:
                score -= 10
            elif issue.severity == IssueSeverity.WARNING:
                score -= 3
            elif issue.severity == IssueSeverity.INFO:
                score -= 0.5

        return max(0.0, min(100.0, score))

    def quick_check(self) -> Dict[str, Any]:
        """Run quick validation check.

        Returns basic statistics without full analysis.

        Returns:
            Quick check results
        """
        return {
            "timestamp": datetime.now().isoformat(),
            "platforms_loaded": {
                "notion": len(self.matcher._notion_tracks),
                "apple_music": len(self.matcher._apple_music_tracks),
                "rekordbox": len(self.matcher._rekordbox_tracks),
                "djay_pro": len(self.matcher._djay_pro_tracks),
            },
            "indexes": {
                "path_index": len(self.matcher._path_index),
                "filename_index": len(self.matcher._filename_index),
                "title_artist_index": len(self.matcher._title_artist_index),
            },
            "status": "ok" if any([
                self.matcher._notion_tracks,
                self.matcher._apple_music_tracks,
            ]) else "no_data",
        }
