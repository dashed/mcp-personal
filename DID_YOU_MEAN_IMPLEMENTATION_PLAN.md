# "Did You Mean?" Feature Implementation Plan

## Overview
Implement an intelligent retry mechanism that detects common parameter misuse patterns and automatically retries the search with corrected parameters, providing a seamless experience for users (especially AI agents) who make common mistakes.

## Goals
1. Automatically detect and correct common parameter mistakes
2. Retry searches with corrected parameters
3. Provide clear feedback about what was corrected
4. Maintain backwards compatibility
5. Make the feature optional/configurable

## Detailed Implementation Plan

### Phase 1: Detection Logic Enhancement

#### 1.1 Enhanced Pattern Detection
```python
class ParameterMisuseDetector:
    """Detects common parameter misuse patterns and suggests corrections."""
    
    def __init__(self):
        self.regex_patterns = [
            # Existing patterns from _looks_like_regex()
            r'\.\*', r'\.\+', r'\\\w', r'\\\d', etc.
        ]
        
        # New: Common mistake patterns
        self.common_mistakes = {
            # Regex in fuzzy_filter
            r'^def\s+\w+.*\(': 'function definitions',
            r'class\s+\w+': 'class definitions',
            r'TODO|FIXME|BUG': 'code markers',
            r'import\s+.*': 'import statements',
        }
    
    def analyze_parameters(self, fuzzy_filter: str, regex_pattern: str) -> Dict[str, Any]:
        """Analyze parameters and return correction suggestions."""
        return {
            'fuzzy_has_regex': self._detect_regex_in_fuzzy(fuzzy_filter),
            'pattern_has_fuzzy': self._detect_fuzzy_in_pattern(regex_pattern),
            'swapped_params': self._detect_swapped_parameters(fuzzy_filter, regex_pattern),
            'suggested_correction': self._suggest_correction(fuzzy_filter, regex_pattern)
        }
```

#### 1.2 Swap Detection Algorithm
```python
def _detect_swapped_parameters(self, fuzzy_filter: str, regex_pattern: str) -> bool:
    """Detect if parameters appear to be swapped."""
    # Check if fuzzy_filter looks like regex AND regex_pattern looks like fuzzy terms
    fuzzy_looks_like_regex = self._looks_like_regex(fuzzy_filter)
    regex_looks_like_fuzzy = self._looks_like_fuzzy_terms(regex_pattern)
    
    # Additional heuristics:
    # - If fuzzy_filter has special regex chars but regex_pattern is simple words
    # - If regex_pattern has no special chars but fuzzy_filter does
    return fuzzy_looks_like_regex and regex_looks_like_fuzzy
```

### Phase 2: Automatic Retry Mechanism

#### 2.1 Retry Configuration
```python
@dataclass
class RetryConfig:
    """Configuration for automatic retry behavior."""
    enabled: bool = True
    max_retries: int = 1
    confidence_threshold: float = 0.8  # How confident we need to be about the correction
    user_consent_required: bool = False  # For interactive mode
```

#### 2.2 Retry Wrapper Functions
```python
def fuzzy_search_content_with_retry(
    fuzzy_filter: str,
    path: str = ".",
    regex_pattern: str = ".",
    hidden: bool = False,
    limit: int = 20,
    rg_flags: str = "",
    multiline: bool = False,
    auto_retry: bool = True,  # New parameter
) -> dict[str, Any]:
    """Enhanced version with automatic retry on parameter misuse."""
    
    # First attempt with original parameters
    result = fuzzy_search_content(
        fuzzy_filter, path, regex_pattern, hidden, limit, rg_flags, multiline
    )
    
    # Check if we should retry
    if auto_retry and _should_retry(result, fuzzy_filter, regex_pattern):
        correction = _get_parameter_correction(fuzzy_filter, regex_pattern)
        
        if correction['confidence'] >= RetryConfig.confidence_threshold:
            # Retry with corrected parameters
            retry_result = fuzzy_search_content(
                correction['fuzzy_filter'],
                path,
                correction['regex_pattern'],
                hidden, limit, rg_flags, multiline
            )
            
            # Add metadata about the correction
            retry_result['did_you_mean'] = {
                'corrected': True,
                'original_fuzzy_filter': fuzzy_filter,
                'original_regex_pattern': regex_pattern,
                'corrected_fuzzy_filter': correction['fuzzy_filter'],
                'corrected_regex_pattern': correction['regex_pattern'],
                'correction_type': correction['type'],
                'confidence': correction['confidence']
            }
            
            return retry_result
    
    return result
```

#### 2.3 Correction Decision Logic
```python
def _should_retry(result: dict, fuzzy_filter: str, regex_pattern: str) -> bool:
    """Determine if we should retry with corrected parameters."""
    # Retry if:
    # 1. No matches found
    # 2. Parameters look suspicious
    # 3. We have high confidence in a correction
    
    no_matches = len(result.get('matches', [])) == 0
    has_warnings = 'warnings' in result
    
    if no_matches or has_warnings:
        analysis = ParameterMisuseDetector().analyze_parameters(fuzzy_filter, regex_pattern)
        return analysis['suggested_correction'] is not None
    
    return False
```

### Phase 3: Correction Strategies

#### 3.1 Parameter Swapping
```python
def _try_parameter_swap(fuzzy_filter: str, regex_pattern: str) -> Tuple[str, str, float]:
    """Try swapping the parameters."""
    # Simply swap them
    new_fuzzy = regex_pattern
    new_regex = fuzzy_filter
    
    # Calculate confidence based on how well they fit their new roles
    confidence = _calculate_swap_confidence(new_fuzzy, new_regex)
    
    return new_fuzzy, new_regex, confidence
```

#### 3.2 Smart Conversion
```python
def _convert_regex_to_fuzzy(regex_pattern: str) -> Tuple[str, float]:
    """Convert regex pattern to fuzzy search terms."""
    # Use existing _suggest_fuzzy_terms() as base
    fuzzy_terms = _suggest_fuzzy_terms(regex_pattern)
    
    # Calculate confidence based on conversion complexity
    confidence = _calculate_conversion_confidence(regex_pattern, fuzzy_terms)
    
    return fuzzy_terms, confidence

def _convert_fuzzy_to_regex(fuzzy_terms: str) -> Tuple[str, float]:
    """Convert fuzzy terms to regex pattern."""
    # Handle common cases
    terms = fuzzy_terms.split()
    
    if len(terms) == 1:
        # Single term - simple contains
        return f".*{re.escape(terms[0])}.*", 0.9
    else:
        # Multiple terms - AND logic
        # "foo bar" -> "(?=.*foo)(?=.*bar)"
        regex = ''.join(f"(?=.*{re.escape(term)})" for term in terms)
        return regex, 0.7
```

### Phase 4: User Feedback Integration

#### 4.1 Response Format with Corrections
```json
{
  "matches": [...],
  "did_you_mean": {
    "corrected": true,
    "message": "Your parameters appeared to be swapped. Automatically retried with corrected parameters.",
    "original": {
      "fuzzy_filter": "def test_.*seer.*credit",
      "regex_pattern": "test seer credit"
    },
    "corrected": {
      "fuzzy_filter": "test seer credit",
      "regex_pattern": "def test_.*seer.*credit"
    },
    "correction_type": "parameter_swap",
    "confidence": 0.95,
    "results_comparison": {
      "original_matches": 0,
      "corrected_matches": 5
    }
  }
}
```

#### 4.2 CLI Interactive Mode
```python
def _handle_interactive_correction(correction: dict) -> bool:
    """Handle interactive correction in CLI mode."""
    if not sys.stdin.isatty():
        return True  # Auto-accept in non-interactive mode
    
    print(f"\n🤔 Did you mean?")
    print(f"  Original: fuzzy_filter='{correction['original_fuzzy']}', "
          f"regex_pattern='{correction['original_regex']}'")
    print(f"  Suggested: fuzzy_filter='{correction['corrected_fuzzy']}', "
          f"regex_pattern='{correction['corrected_regex']}'")
    
    response = input("\nTry with corrected parameters? [Y/n]: ")
    return response.lower() != 'n'
```

### Phase 5: Learning and Improvement

#### 5.1 Usage Analytics (Optional)
```python
class UsageAnalytics:
    """Track parameter corrections for improving detection."""
    
    def log_correction(self, original: dict, corrected: dict, accepted: bool):
        """Log correction attempts for analysis."""
        # This could write to a local file or memory
        # Used to improve correction algorithms over time
        pass
```

#### 5.2 Confidence Scoring
```python
def _calculate_correction_confidence(original: dict, corrected: dict) -> float:
    """Calculate confidence score for a correction."""
    score = 0.0
    
    # Factors that increase confidence:
    # 1. Original parameters have clear misuse patterns
    if _looks_like_regex(original['fuzzy_filter']):
        score += 0.3
    
    # 2. Corrected parameters look appropriate
    if not _looks_like_regex(corrected['fuzzy_filter']):
        score += 0.3
    
    # 3. Pattern complexity matches expected usage
    if _is_simple_pattern(corrected['regex_pattern']):
        score += 0.2
    
    # 4. Historical success rate (if analytics enabled)
    # score += _get_historical_success_rate(pattern_type)
    
    return min(score, 1.0)
```

### Phase 6: Configuration and Control

#### 6.1 Environment Variables
```python
# Allow users to control retry behavior
AUTO_RETRY_ENABLED = os.getenv('MCP_FUZZY_SEARCH_AUTO_RETRY', 'true').lower() == 'true'
RETRY_CONFIDENCE_THRESHOLD = float(os.getenv('MCP_FUZZY_SEARCH_RETRY_CONFIDENCE', '0.8'))
```

#### 6.2 MCP Tool Parameters
```python
@mcp.tool(
    description="...",
    extra_params={
        "auto_correct": {
            "type": "boolean",
            "default": True,
            "description": "Automatically retry with corrected parameters if misuse detected"
        }
    }
)
```

## Implementation Timeline

### Week 1: Core Detection
- Implement enhanced parameter analysis
- Create correction suggestion algorithms
- Unit tests for detection logic

### Week 2: Retry Mechanism
- Implement retry wrapper functions
- Add confidence scoring
- Integration tests

### Week 3: User Experience
- Add interactive mode for CLI
- Implement response formatting
- Create documentation

### Week 4: Testing and Refinement
- End-to-end testing
- Performance optimization
- Edge case handling

## Potential Challenges

1. **False Positives**: May incorrectly "correct" valid but unusual parameter usage
   - Solution: Conservative confidence thresholds, user override options

2. **Performance Impact**: Additional analysis and potential retry adds latency
   - Solution: Quick detection heuristics, optional feature

3. **User Confusion**: Automatic corrections might be unexpected
   - Solution: Clear messaging, opt-in behavior

4. **Complex Patterns**: Some regex patterns are hard to convert to fuzzy terms
   - Solution: Only attempt correction for high-confidence cases

## Success Metrics

1. **Reduction in failed searches** due to parameter misuse
2. **Improved user experience** for AI agents
3. **Reduced support questions** about parameter usage
4. **High accuracy** of automatic corrections (>90%)

## Future Enhancements

1. **Machine Learning**: Train a model on usage patterns for better detection
2. **Multi-language Support**: Detect patterns in different languages
3. **Context Awareness**: Use file types and content to improve corrections
4. **Batch Operations**: Apply learned corrections to multiple searches