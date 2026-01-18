# Monolithic Script Maintenance Plan

**Date:** 2026-01-08
**Status:** IN PROGRESS - Maintenance Ongoing
**Last Audit:** 2026-01-14 06:01:00
**Target Script:** `monolithic-scripts/soundcloud_download_prod_merge-2.py`
**Created By:** Plans Directory Audit Agent (Gap Reconciliation)

---

## Executive Summary

This document outlines the maintenance plan for the monolithic music download script while the bifurcation strategy is being implemented. The goal is to ensure stability, fix critical bugs, and maintain backward compatibility during the transition period.

---

## Current State Assessment

### Script Overview

| Property | Value |
|----------|-------|
| File | `soundcloud_download_prod_merge-2.py` |
| Location | `/monolithic-scripts/` |
| Size | 413,280 bytes |
| Lines | ~8,500+ |
| Last Modified | 2026-01-08 11:07 |
| Status | Production-ready |

### Feature Inventory

**Core Features:**
- Multi-source download (SoundCloud, YouTube, Spotify)
- Comprehensive deduplication (Notion + Eagle + Fingerprint)
- Metadata extraction and enrichment
- Multi-format output (M4A, WAV, AIFF)
- Playlist-based organization

**Integration Points:**
- Notion API (database queries, page updates)
- Eagle API (library import, tagging)
- Spotify API (metadata enrichment)
- yt-dlp (download engine)

---

## Known Issues

### Critical Issues

| Issue | Severity | Description | Status |
|-------|----------|-------------|--------|
| DRM Error Handling | CRITICAL | Spotify URLs cause DRM errors | OPEN |
| URL Normalization | HIGH | YouTube URL parsing issues (previously fixed) | RESOLVED |
| get_page() Method | HIGH | Missing NotionClient method | RESOLVED |

### Medium Issues

| Issue | Severity | Description | Status |
|-------|----------|-------------|--------|
| unified_config Warning | MEDIUM | Module not found warning | ACCEPTABLE (uses fallback) |
| unified_state_registry | MEDIUM | Module not found | ACCEPTABLE (uses fallback) |
| Smart Eagle API | MEDIUM | Not available warning | ACCEPTABLE (uses fallback) |
| Volume Index Missing | MEDIUM | Index file not found | OPEN |

### Low Priority Issues

| Issue | Severity | Description | Status |
|-------|----------|-------------|--------|
| pkg_resources Deprecation | LOW | Python library warning | MONITOR |
| Large File Size | LOW | 8,500+ lines | DEFERRED (bifurcation) |

---

## Maintenance Tasks

### Immediate (Priority 1)

1. **Fix DRM Error Handling**
   - Implement YouTube search fallback for Spotify tracks
   - Add proper error classification
   - Implement retry with alternative source

2. **Create Volume Index File**
   - Path: `/var/music_volume_index.json`
   - Structure: Track metadata index
   - Purpose: Performance optimization

3. **Document Environment Requirements**
   - Create `.env.example` with all required variables
   - Document `TRACKS_DB_ID` requirement
   - Document optional vs required variables

### Short-Term (Priority 2)

4. **Improve Error Logging**
   - Standardize error message format
   - Add error classification
   - Implement structured logging

5. **Add Input Validation**
   - Validate URLs before processing
   - Validate Notion page IDs
   - Add rate limiting protection

6. **Performance Profiling**
   - Profile critical paths
   - Identify bottlenecks
   - Document performance baseline

### Long-Term (Priority 3)

7. **Code Documentation**
   - Add docstrings to key functions
   - Document complex logic
   - Create API documentation

8. **Test Coverage**
   - Add unit tests for critical functions
   - Add integration tests for workflows
   - Set up CI/CD testing

---

## Bug Fix Procedures

### Critical Bug Process

1. **Identify**: Log analysis, user report, or monitoring alert
2. **Reproduce**: Create minimal reproduction case
3. **Document**: Update known issues table
4. **Fix**: Implement fix with minimal changes
5. **Test**: Verify fix doesn't introduce regressions
6. **Deploy**: Update production script
7. **Monitor**: Watch for related issues

### Change Control

- All changes documented in changelog
- Version number incremented for each fix
- Backup created before modifications
- Rollback plan documented

---

## Performance Baseline

### Current Metrics (from 2026-01-08 execution)

| Metric | Value |
|--------|-------|
| Workflow Duration | ~30 seconds |
| Notion API Calls | Variable |
| Files Processed | Variable |
| Success Rate | ~95% (with fallbacks) |

### Target Metrics

| Metric | Target |
|--------|--------|
| Workflow Duration | < 60 seconds |
| API Error Rate | < 5% |
| Success Rate | > 90% |
| Memory Usage | < 1GB |

---

## Compatibility Requirements

### Backward Compatibility

- Maintain all existing CLI arguments
- Preserve processing modes (single, batch, all, reprocess, url)
- Keep file output formats unchanged
- Preserve Notion property names

### Forward Compatibility

- Design for modular extraction
- Use abstraction layers where possible
- Minimize dependencies on global state
- Document all integration points

---

## Support Procedures

### Troubleshooting Guide

**Common Issues:**

1. **"DRM protection" error**
   - Cause: Direct Spotify URL processing
   - Solution: Use `--mode single` or search YouTube

2. **"unified_config unavailable" warning**
   - Cause: Module not in path
   - Solution: Acceptable - uses fallback

3. **"Rate limit exceeded" error**
   - Cause: Too many API requests
   - Solution: Wait and retry, reduce batch size

4. **"Track not found in Notion" error**
   - Cause: Track not added to database
   - Solution: Add track manually or use playlist sync

### Escalation Path

1. Check known issues table
2. Review execution logs
3. Create Issue in Issues+Questions database
4. Escalate to development agent

---

## Changelog

### Version History

| Version | Date | Changes |
|---------|------|---------|
| Current | 2026-01-08 | Production stable with known issues |
| Previous | 2026-01-06 | URL normalization fix |

---

## Next Steps

1. [ ] Fix DRM error handling (Critical)
2. [ ] Create volume index file
3. [ ] Document environment requirements
4. [ ] Set up performance monitoring
5. [ ] Create test suite foundation

---

**Document Status:** DRAFT
**Requires:** Implementation of maintenance tasks
**Created During:** Plans Directory Audit 2026-01-08
