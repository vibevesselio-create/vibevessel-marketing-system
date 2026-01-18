# Dynamic Discovery Workflow Architecture

## Executive Summary

This document defines a **discovery-based, self-optimizing workflow system** that continuously identifies, prioritizes, and resolves Agent-Projects, Agent-Tasks, and Issues across the entire VibeVessel automation ecosystem. The system operates without requiring specific targets, instead dynamically discovering work through gap analysis, performance metrics, and cross-system synchronization audits.

---

## 1. Core Workflow Phases

### Phase 1: Discovery & Audit
**Purpose:** Systematically discover work items, gaps, and optimization opportunities

```
┌─────────────────────────────────────────────────────────────────────┐
│                     DISCOVERY ENGINE                                 │
├─────────────────────────────────────────────────────────────────────┤
│  1. Notion Database Scan                                            │
│     ├── Agent-Projects (status != Completed)                        │
│     ├── Agent-Tasks (status != Completed)                           │
│     ├── Issues+Questions (status = Open)                            │
│     └── Services (gaps in properties/relations)                     │
│                                                                     │
│  2. Codebase Audit                                                  │
│     ├── Orphaned scripts (not in Scripts DB)                        │
│     ├── Missing documentation                                       │
│     ├── Unlinked API functions                                      │
│     └── Module gap analysis (music_workflow, image_workflow, etc.)  │
│                                                                     │
│  3. Cross-System Sync Check                                         │
│     ├── Linear ↔ Notion alignment                                   │
│     ├── GitHub ↔ Notion alignment                                   │
│     ├── Services ↔ Scripts linkage                                  │
│     └── Google Account credential status                            │
└─────────────────────────────────────────────────────────────────────┘
```

### Phase 2: Prioritization & Planning
**Purpose:** Score and sequence discovered work for maximum impact

```
Priority Score = (Impact × Urgency × Dependencies_Ready) / Complexity

Factors:
├── Impact: Business value, system stability, user-facing
├── Urgency: Deadlines, blocking other work, decay rate
├── Dependencies_Ready: Prerequisites completed (0 or 1)
└── Complexity: Estimated effort, risk level
```

### Phase 3: Execution & Resolution
**Purpose:** Execute work items through structured agent handoffs

```
┌─────────────────────────────────────────────────────────────────────┐
│                    EXECUTION ENGINE                                  │
├─────────────────────────────────────────────────────────────────────┤
│  Task Type Routing:                                                 │
│  ├── Code Implementation → Claude Code Agent                        │
│  ├── Documentation → Documentation Agent                            │
│  ├── Database Updates → Notion Sync Agent                           │
│  ├── API Integration → API Integration Agent                        │
│  └── Review/Audit → Review Agent                                    │
│                                                                     │
│  Execution Pattern:                                                 │
│  1. Create detailed task specification                              │
│  2. Execute with progress tracking                                  │
│  3. Validate output against success criteria                        │
│  4. Update all affected databases                                   │
│  5. Create handoff tasks for follow-up work                         │
└─────────────────────────────────────────────────────────────────────┘
```

### Phase 4: Metrics & Review
**Purpose:** Measure performance and identify optimization opportunities

```
┌─────────────────────────────────────────────────────────────────────┐
│                    METRICS ENGINE                                    │
├─────────────────────────────────────────────────────────────────────┤
│  Performance Metrics:                                               │
│  ├── Task completion rate (daily/weekly)                            │
│  ├── Average resolution time                                        │
│  ├── Issue recurrence rate                                          │
│  ├── Cross-system sync accuracy                                     │
│  └── Gap closure velocity                                           │
│                                                                     │
│  Quality Metrics:                                                   │
│  ├── Code coverage for new modules                                  │
│  ├── Documentation completeness                                     │
│  ├── Database property fill rate                                    │
│  └── Relation linkage completeness                                  │
│                                                                     │
│  System Health:                                                     │
│  ├── API credential expiration status                               │
│  ├── Service availability                                           │
│  ├── Sync lag times                                                 │
│  └── Error rates by component                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Phase 5: Self-Optimization
**Purpose:** Continuously improve the workflow based on metrics

```
Optimization Triggers:
├── High recurrence rate → Create preventive automation
├── Slow resolution time → Decompose task patterns
├── Low sync accuracy → Strengthen validation rules
├── Repeated gaps → Add to standard audit checklist
└── Performance degradation → Trigger architecture review
```

---

## 2. Services Database Synchronization

### Gap Analysis Framework

```python
class ServicesGapAnalyzer:
    """Identifies gaps in Services database entries."""

    REQUIRED_PROPERTIES = [
        "Name", "Description", "Status", "Primary Type",
        "API Docs Homepage URL", "Auth Method Standardized",
        "Environment Key", "scripts", "Agent-Workflows"
    ]

    RECOMMENDED_RELATIONS = [
        "scripts",           # Link to implementation scripts
        "Agent-Workflows",   # Link to automation workflows
        "Agent-Functions",   # Link to API function definitions
        "Documents",         # Link to documentation
        "Variables"          # Link to required env variables
    ]

    def analyze_service(self, service_page):
        gaps = []

        # Check required properties
        for prop in self.REQUIRED_PROPERTIES:
            if not service_page.get(prop):
                gaps.append(f"Missing: {prop}")

        # Check relations
        for relation in self.RECOMMENDED_RELATIONS:
            if not service_page.get_relations(relation):
                gaps.append(f"Unlinked: {relation}")

        return gaps
```

### Service Categories Mapping

| Category | Services | Required Relations |
|----------|----------|-------------------|
| **Authentication** | OAuth, API Keys | Variables, Credentials |
| **Storage** | Google Drive, Eagle, Lightroom | sync-DBs, folders |
| **Communication** | Slack, Email | Agent-Workflows, Webhooks |
| **Issue Tracking** | Linear, GitHub Issues | Agent-Tasks, scripts |
| **Database** | Notion, SQL | system-databases, sync-DBs |
| **Media** | YouTube, SoundCloud, Spotify | Agent-Functions, scripts |

---

## 3. Multi-Environment Synchronization Map

### Google Account Routing

```
┌─────────────────────────────────────────────────────────────────────┐
│                 GOOGLE ACCOUNT ROUTING                               │
├─────────────────────────────────────────────────────────────────────┤
│  Account: brian@serenmedia.co                                       │
│  ├── Project: seventh-atom-435416-u5                                │
│  ├── Services: YouTube API, Google Drive, Apps Script               │
│  └── Token: google_oauth_token_brian_at_serenmedia_co.pickle        │
│                                                                     │
│  Account: vibe.vessel.io@gmail.com                                  │
│  ├── Project: (legacy OAuth)                                        │
│  ├── Services: Google Drive (storage), Photos                       │
│  └── Token: google_oauth_token_vibe_vessel_io_at_gmail_com.pickle   │
├─────────────────────────────────────────────────────────────────────┤
│  Routing Logic:                                                     │
│  ├── YouTube API → brian@serenmedia.co (API quotas)                 │
│  ├── Drive Storage (automation) → vibe.vessel.io@gmail.com          │
│  ├── Drive Storage (client) → client-specific account               │
│  └── Apps Script Deployment → brian@serenmedia.co                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Database Synchronization Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Lightroom  │     │    Eagle     │     │ Google Drive │
│   Catalog    │     │   Library    │     │    Photos    │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────┬───────┴───────┬────────────┘
                    ▼               ▼
            ┌───────────────────────────────┐
            │     Central Sync Database     │
            │   (SQLite on Google Drive)    │
            └───────────────┬───────────────┘
                            │
                            ▼
            ┌───────────────────────────────┐
            │    Notion Photo Library       │
            │  (VibeVessel-Automation)      │
            └───────────────────────────────┘
```

---

## 4. Workflow Module Implementation Pattern

### Standard Module Structure

```
{domain}_workflow/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── models.py          # Domain data models
│   ├── orchestrator.py    # Main workflow coordinator
│   └── dispatcher.py      # Task routing
├── integrations/
│   ├── __init__.py
│   ├── notion.py          # Notion integration
│   ├── {service_1}.py     # Service-specific integration
│   └── {service_2}.py
├── deduplication/
│   ├── __init__.py
│   ├── fingerprint.py     # Identity resolution
│   └── matcher.py         # Duplicate detection
├── utils/
│   ├── __init__.py
│   ├── errors.py          # Custom exceptions
│   └── validators.py      # Input validation
├── config/
│   ├── __init__.py
│   ├── settings.py        # Environment-based config
│   └── constants.py       # Domain constants
└── tests/
    ├── unit/
    └── integration/
```

### YouTube Workflow Module (To Be Implemented)

```
youtube_workflow/
├── __init__.py
├── core/
│   ├── models.py          # VideoInfo, PlaylistInfo, ChannelInfo
│   ├── orchestrator.py    # YouTube sync coordinator
│   └── search.py          # Multi-strategy search
├── integrations/
│   ├── youtube_api.py     # YouTube Data API v3 client
│   ├── yt_dlp.py          # yt-dlp wrapper
│   └── notion.py          # Notion sync
├── deduplication/
│   ├── fingerprint.py     # Video fingerprinting
│   └── matcher.py         # Duration-based matching
├── utils/
│   ├── errors.py
│   └── account_router.py  # Google account selection
└── config/
    ├── settings.py        # YOUTUBE_API_KEY, account config
    └── constants.py       # Platform enum, search strategies
```

---

## 5. Task Resolution Engine

### Automatic Task Discovery

```python
class TaskDiscoveryEngine:
    """Discovers actionable tasks from multiple sources."""

    def discover_tasks(self) -> List[DiscoveredTask]:
        tasks = []

        # 1. Notion Agent-Tasks (explicit tasks)
        tasks.extend(self._scan_agent_tasks())

        # 2. Notion Issues+Questions (problems to solve)
        tasks.extend(self._scan_issues())

        # 3. Services Database Gaps (missing properties/relations)
        tasks.extend(self._analyze_services_gaps())

        # 4. Codebase Gaps (unlinked scripts, missing modules)
        tasks.extend(self._analyze_codebase_gaps())

        # 5. Sync Drift (out-of-sync cross-system state)
        tasks.extend(self._detect_sync_drift())

        return self._prioritize(tasks)

    def _prioritize(self, tasks: List[DiscoveredTask]) -> List[DiscoveredTask]:
        """Sort tasks by impact, urgency, and readiness."""
        for task in tasks:
            task.priority_score = self._calculate_priority(task)

        return sorted(tasks, key=lambda t: t.priority_score, reverse=True)
```

### Task Execution Loop

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TASK EXECUTION LOOP                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  while has_available_context:                                       │
│      1. DISCOVER: Scan all sources for tasks                        │
│      2. SELECT: Pick highest-priority task with ready dependencies  │
│      3. PLAN: Generate execution plan with success criteria         │
│      4. EXECUTE: Perform task with progress tracking                │
│      5. VALIDATE: Check output against success criteria             │
│      6. UPDATE: Sync all affected databases                         │
│      7. HANDOFF: Create follow-up tasks if needed                   │
│      8. METRICS: Record performance data                            │
│      9. OPTIMIZE: Adjust priorities based on outcomes               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 6. Performance Review Framework

### Metrics Collection

```python
@dataclass
class WorkflowMetrics:
    """Metrics for workflow performance review."""

    # Task Metrics
    tasks_discovered: int = 0
    tasks_completed: int = 0
    tasks_blocked: int = 0
    avg_resolution_time_hours: float = 0.0

    # Gap Metrics
    services_gaps_identified: int = 0
    services_gaps_resolved: int = 0
    scripts_linked: int = 0
    relations_created: int = 0

    # Quality Metrics
    validation_pass_rate: float = 0.0
    recurrence_rate: float = 0.0
    documentation_coverage: float = 0.0

    # System Health
    sync_accuracy: float = 0.0
    api_success_rate: float = 0.0
    error_count: int = 0
```

### Review Cadence

| Review Type | Frequency | Focus Areas |
|-------------|-----------|-------------|
| **Task Batch** | Per execution | Completion, blockers, handoffs |
| **Daily Summary** | Daily | Velocity, patterns, anomalies |
| **Weekly Audit** | Weekly | Gap closure, sync accuracy, trends |
| **Monthly Review** | Monthly | System health, optimization opportunities |

### Self-Correction Triggers

```python
class SelfCorrectionEngine:
    """Triggers optimization based on metrics."""

    THRESHOLDS = {
        "recurrence_rate": 0.15,      # >15% triggers automation
        "resolution_time_hours": 48,   # >48h triggers decomposition
        "sync_accuracy": 0.95,         # <95% triggers validation review
        "validation_pass_rate": 0.90,  # <90% triggers criteria review
    }

    def evaluate(self, metrics: WorkflowMetrics) -> List[Optimization]:
        optimizations = []

        if metrics.recurrence_rate > self.THRESHOLDS["recurrence_rate"]:
            optimizations.append(
                Optimization(
                    type="CREATE_AUTOMATION",
                    reason="High recurrence rate detected",
                    action="Create preventive automation for recurring issues"
                )
            )

        # ... additional evaluations

        return optimizations
```

---

## 7. Implementation Roadmap

### Phase 1: Foundation (Current Session)
- [x] image_workflow module structure
- [x] Linear/GitHub orchestrator dependencies
- [x] Services database gap analysis framework
- [ ] youtube_workflow module structure
- [ ] Dynamic discovery engine

### Phase 2: Integration (Next Session)
- [ ] Services ↔ Scripts bidirectional sync
- [ ] API Functions ↔ Services linking
- [ ] Multi-Google account router
- [ ] Notion sync for all workflow modules

### Phase 3: Automation (Future)
- [ ] Scheduled discovery runs
- [ ] Automatic task creation from gaps
- [ ] Self-optimization triggers
- [ ] Performance dashboard

### Phase 4: Optimization (Ongoing)
- [ ] Machine learning for prioritization
- [ ] Predictive gap detection
- [ ] Automated documentation generation
- [ ] Cross-project pattern recognition

---

## 8. Database Property Requirements

### Services Database (26ce7361-6c27-8134-8909-ee25246dfdc4)

**Required for Gap Analysis:**
| Property | Type | Purpose |
|----------|------|---------|
| Name | title | Service identifier |
| Status | status | Active/Inactive/Deprecated |
| API Docs Homepage URL | url | Documentation access |
| Auth Method Standardized | select | OAuth/API Key/None |
| Environment Key | rich_text | Env var prefix |
| scripts | relation | Implementation scripts |
| Agent-Workflows | relation | Automation workflows |
| Agent-Functions | relation | API function definitions |
| Documents | relation | Documentation links |

**New Properties to Add:**
| Property | Type | Purpose |
|----------|------|---------|
| Gap Score | number | Computed completeness |
| Last Audit Date | date | When last reviewed |
| Google Account | select | Which account to use |
| Workflow Module | rich_text | Associated module path |

---

## 9. Handoff Task Template

```markdown
## Task: [Title]

### Context
[Brief description of what led to this task]

### Success Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

### Technical Details
- Files: [list of relevant files]
- Databases: [Notion databases affected]
- Dependencies: [prerequisite tasks]

### Execution Notes
- [Key considerations]
- [Known blockers]
- [Recommended approach]

### Metrics to Track
- [What to measure]
- [Expected outcomes]
```

---

## 10. Conclusion

This Dynamic Discovery Workflow Architecture provides:

1. **Automatic Discovery** - No specific targets needed; work is found through systematic audits
2. **Prioritized Execution** - Impact-based scoring ensures highest-value work first
3. **Cross-System Synchronization** - Services, Scripts, Workflows all stay linked
4. **Performance Review** - Dedicated metrics collection and analysis
5. **Self-Optimization** - Automatic triggers for process improvement

The system continuously improves by:
- Learning from task patterns
- Identifying recurring issues
- Closing gaps systematically
- Maintaining cross-system accuracy
- Generating preventive automations

---

*Document Version: 1.0*
*Created: 2026-01-18*
*Author: Claude Code Agent (Opus)*
