#!/bin/bash
# Quick script to verify item_map fix is working

DB="$HOME/Library/Application Support/ca.tubb.fichero/library/library.db"

echo "🔍 Checking recent processing..."
echo ""

# Get latest processing
LATEST=$(sqlite3 "$DB" "SELECT id FROM processing_results ORDER BY created_at DESC LIMIT 1;" 2>/dev/null)

if [ -z "$LATEST" ]; then
    echo "❌ No processing results found"
    echo "   Process a folder first, then run this script again"
    exit 1
fi

echo "📊 Processing Result ID: $LATEST"
echo ""

# Check routing
UNIQUE=$(sqlite3 "$DB" "SELECT COUNT(DISTINCT item_id) FROM processing_outputs WHERE processing_result_id = '$LATEST' AND output_type = 'transcription';" 2>/dev/null)
TOTAL=$(sqlite3 "$DB" "SELECT COUNT(*) FROM processing_outputs WHERE processing_result_id = '$LATEST' AND output_type = 'transcription';" 2>/dev/null)

echo "📝 Transcription outputs:"
echo "   Unique items: $UNIQUE"
echo "   Total outputs: $TOTAL"
echo ""

if [ "$UNIQUE" -eq "$TOTAL" ] && [ "$TOTAL" -gt 0 ]; then
    echo "✅ FIX IS WORKING!"
    echo "   Each file has its own unique transcription."
    echo ""

    # Show sample
    echo "Sample routing (first 3):"
    sqlite3 "$DB" "SELECT ci.type, ci.name, po.output_type FROM processing_outputs po JOIN collection_items ci ON po.item_id = ci.id WHERE po.processing_result_id = '$LATEST' LIMIT 3;" 2>/dev/null | while read line; do
        echo "   $line"
    done

elif [ "$UNIQUE" -eq 1 ] && [ "$TOTAL" -gt 1 ]; then
    echo "❌ BUG STILL PRESENT!"
    echo "   All $TOTAL transcriptions going to same item (likely folder)."
    echo ""
    echo "Troubleshooting:"
    echo "   1. Run: ./clear_cache.sh"
    echo "   2. Kill app: pkill -f fichero"
    echo "   3. Restart: briefcase dev"
    echo "   4. Process NEW folder (not old data)"

elif [ "$TOTAL" -eq 0 ]; then
    echo "ℹ️  No transcriptions found in latest processing"
    echo "   This might be a catalogue-only workflow"

else
    echo "⚠️  Unexpected results"
    echo "   Unique: $UNIQUE, Total: $TOTAL"
    echo "   Check manually with: sqlite3 \"$DB\""
fi

echo ""
