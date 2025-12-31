# NSLog → OSLog Replacement Guide

## Completed (45/88)

### Models Layer ✅ (10 instances)
- **DocumentStore.swift** (9 instances) - Added Logger, replaced all NSLog
- **WorkflowStore.swift** (1 instance) - Added Logger, replaced NSLog

### Views/Sidebar Layer ✅ (9 instances)
- **SidebarView.swift** (8 instances) - Had Logger, replaced NSLog
- **SidebarItemRow.swift** (1 instance) - Had Logger, replaced NSLog

### Views/Chat Layer ✅ (4 instances)
- **ChatInspector.swift** (4 instances) - Added Logger, replaced all NSLog

### Views/Library Layer ✅ (6 instances)
- **FolderAccessManager.swift** (5 instances) - Added Logger, replaced all NSLog
- **DocumentTabView.swift** (1 instance) - Added Logger, replaced NSLog

### Services Layer ✅ (16 instances)
- **APIClient.swift** (15 instances) - Added Logger, replaced all NSLog
- **WorkflowService.swift** (1 instance) - Added Logger, replaced NSLog

**Build Status**: ✅ Succeeded

## Remaining (43/88)

### Pattern to Follow

1. **Add OSLog import** (if not present):
```swift
import OSLog
```

2. **Add Logger instance** (if not present):
```swift
private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ClassName")
```

3. **Replace NSLog calls**:
```swift
// OLD:
NSLog("[Tag] Message")
NSLog("[Tag] Value: %@", someValue)
NSLog("[Tag] Count: %d", count)

// NEW:
logger.info("Message")
logger.info("Value: \(someValue)")  
logger.info("Count: \(count)")

// For errors:
logger.error("ERROR: \(String(describing: error))")

// For warnings:
logger.warning("WARNING: Something happened")
```

4. **Handle property interpolation** - Use `self.` for properties:
```swift
// In closures or where Swift requires explicit self:
logger.info("Count: \(self.collections.count)")
```

### Remaining Views Files

- **Views/AIProviders/AddProviderSheet.swift** (11 instances)
- **Views/ContentView.swift** (9 instances)
- **Views/AIProviders/ProvidersView.swift** (7 instances)
- **Views/Search/SearchView.swift** (6 instances)
- **Views/Workflow/WorkflowInspector.swift** (2 instances)
- **Views/Library/QuickLookComponents.swift** (2 instances)
- **Views/AIProviders/AIModelSelectionView.swift** (2 instances)
- **Views/Workflow/NodePopover.swift** (1 instance)
- **Views/AIProviders/AIProviderAddModelsSheet.swift** (1 instance)
- **Views/AIProviders/AIModelCatalog.swift** (1 instance)

**Total Remaining**: 43 instances

## Automation Script

```bash
#!/bin/bash
# Replace NSLog with logger in a file

FILE="$1"

# Check if file has OSLog
if ! grep -q "import OSLog" "$FILE"; then
    # Add import after other imports
    sed -i '' '/^import /a\
import OSLog
' "$FILE"
fi

# Check if file has Logger
if ! grep -q "Logger(subsystem:" "$FILE"; then
    # Extract class/struct name
    CLASSNAME=$(grep -E "^(class|struct|actor)" "$FILE" | head -1 | awk '{print $2}' | cut -d: -f1)
    # Add logger property
    # This is tricky, would need manual addition
    echo "Manual step: Add logger to $FILE for class $CLASSNAME"
fi

# Replace NSLog patterns
sed -i '' 's/NSLog("\[\([^]]*\)\] \([^"]*\)", \([^)]*\))/logger.info("\2", \3)/g' "$FILE"
sed -i '' 's/NSLog("\[\([^]]*\)\] \([^"]*\)")/logger.info("\2")/g' "$FILE"
sed -i '' 's/NSLog("\[\([^]]*\)\] ERROR/logger.error("/g' "$FILE"
sed -i '' 's/NSLog("\[\([^]]*\)\] WARNING/logger.warning("/g' "$FILE"

echo "Processed $FILE - check for manual fixes needed"
```

## Testing

After each file/layer:
1. Build: `xcodebuild -project Fichero/Fichero.xcodeproj -scheme Fichero build`
2. Run app and check Console.app for structured logs
3. Verify log levels (info, error, warning) appear correctly

## Benefits of OSLog

1. **Performance**: Faster than NSLog, optimized by Apple
2. **Privacy**: Automatic redaction of sensitive data
3. **Structure**: Categories and subsystems for organization
4. **Levels**: debug, info, error, fault for filtering
5. **Console.app**: Better integration with system logging
6. **Instruments**: Can be used with logging profiling tools

