#!/bin/bash
# split_pdf_for_mineru.sh
# 自动分割 PDF 使每个 chunk < 1MB（MinerU OSS 上传限制）
# 使用 pdftk burst 正确分割，然后合并页面到接近 1MB

set -e

# 配置
MAX_SIZE_MB=1.0
MAX_SIZE_BYTES=$(echo "$MAX_SIZE_MB * 1024 * 1024" | bc | cut -d. -f1)

# 参数检查
if [ $# -lt 2 ]; then
    echo "Usage: $0 <input.pdf> <output_dir> [--keep-pages]"
    echo ""
    echo "Options:"
    echo "  --keep-pages    保留分割后的单页 PDF（用于调试）"
    echo ""
    echo "Example:"
    echo "  $0 /tmp/paper.pdf /tmp/paper_chunks"
    exit 1
fi

INPUT_PDF="$1"
OUTPUT_DIR="$2"
KEEP_PAGES=false

if [ "$3" = "--keep-pages" ]; then
    KEEP_PAGES=true
fi

# 检查输入文件
if [ ! -f "$INPUT_PDF" ]; then
    echo "❌ Error: Input file not found: $INPUT_PDF"
    exit 1
fi

# 检查必要工具
if ! command -v pdftk &> /dev/null; then
    echo "❌ Error: pdftk not found. Install with: apt-get install pdftk-java"
    exit 1
fi

# 获取 PDF 信息
PDF_SIZE=$(wc -c < "$INPUT_PDF")
PDF_SIZE_MB=$(echo "$PDF_SIZE" | awk '{printf "%.1f", $1/1024/1024}')
PAGE_COUNT=$(pdfinfo "$INPUT_PDF" 2>/dev/null | grep "Pages:" | awk '{print $2}' || echo "unknown")

echo "📄 Input PDF: $INPUT_PDF"
echo "   Size: $PDF_SIZE_MB MB"
echo "   Pages: $PAGE_COUNT"
echo ""

# 如果文件 < 1MB，无需分割
if [ $PDF_SIZE -lt $MAX_SIZE_BYTES ]; then
    echo "✅ PDF < 1MB, no split needed"
    mkdir -p "$OUTPUT_DIR"
    cp "$INPUT_PDF" "$OUTPUT_DIR/chunk_0.pdf"
    echo "   Output: $OUTPUT_DIR/chunk_0.pdf"
    exit 0
fi

echo "⚠️  PDF > 1MB, splitting into chunks..."
echo ""

# 创建临时目录
TEMP_DIR=$(mktemp -d)
mkdir -p "$OUTPUT_DIR"

# Step 1: 使用 pdftk burst 分割为单页（正确的方法）
echo "Step 1: Splitting into single pages (pdftk burst)..."
pdftk "$INPUT_PDF" burst output "$TEMP_DIR/page_%03d.pdf" 2>/dev/null

# 统计页数
PAGE_FILES=$(ls "$TEMP_DIR"/page_*.pdf | sort)
PAGE_COUNT=$(echo "$PAGE_FILES" | wc -l)
echo "   Split into $PAGE_COUNT pages"

# Step 2: 收集页面大小信息
echo ""
echo "Step 2: Analyzing page sizes..."

declare -a PAGE_SIZES
declare -a PAGE_FILES_ARRAY

idx=0
for page_file in $PAGE_FILES; do
    size=$(wc -c < "$page_file")
    PAGE_SIZES[$idx]=$size
    PAGE_FILES_ARRAY[$idx]=$page_file
    idx=$((idx + 1))
done

# Step 3: 合并页面为 chunks（贪心算法，每个 chunk 尽可能接近 1MB）
echo ""
echo "Step 3: Merging pages into chunks (< 1MB, greedy packing)..."

chunk_id=0
current_files=""
current_size=0
page_start=0

for i in $(seq 0 $(($PAGE_COUNT - 1))); do
    page_file="${PAGE_FILES_ARRAY[$i]}"
    page_size="${PAGE_SIZES[$i]}"
    
    # 检查添加这一页后是否超过限制
    new_size=$((current_size + page_size))
    
    if [ $new_size -gt $MAX_SIZE_BYTES ] && [ -n "$current_files" ]; then
        # 当前 chunk 已满，输出并开始新 chunk
        if [ $chunk_id -eq 0 ]; then
            output_file="$OUTPUT_DIR/chunk_0.pdf"
        else
            output_file="$OUTPUT_DIR/chunk_$chunk_id.pdf"
        fi
        
        pdftk $current_files cat output "$output_file" 2>/dev/null
        
        chunk_size=$(wc -c < "$output_file")
        chunk_mb=$(echo $chunk_size | awk '{printf "%.2f", $1/1024/1024}')
        page_end=$((i))
        page_num_start=$((page_start + 1))
        page_num_end=$page_end
        echo "   Chunk $chunk_id (pages $page_num_start-$page_num_end): $chunk_mb MB"
        
        # 重置
        chunk_id=$((chunk_id + 1))
        current_files="$page_file"
        current_size=$page_size
        page_start=$i
    else
        # 添加到当前 chunk
        if [ -z "$current_files" ]; then
            current_files="$page_file"
        else
            current_files="$current_files $page_file"
        fi
        current_size=$new_size
    fi
done

# 输出最后一个 chunk
if [ -n "$current_files" ]; then
    output_file="$OUTPUT_DIR/chunk_$chunk_id.pdf"
    pdftk $current_files cat output "$output_file" 2>/dev/null
    
    chunk_size=$(wc -c < "$output_file")
    chunk_mb=$(echo $chunk_size | awk '{printf "%.2f", $1/1024/1024}')
    page_num_start=$((page_start + 1))
    page_num_end=$PAGE_COUNT
    echo "   Chunk $chunk_id (pages $page_num_start-$page_num_end): $chunk_mb MB"
fi

# Step 4: 检查并压缩超过限制的 chunk
echo ""
echo "Step 4: Checking for oversized chunks..."
OVERSIZED=$(find "$OUTPUT_DIR" -name "chunk_*.pdf" -size +${MAX_SIZE_BYTES}c 2>/dev/null | wc -l)

if [ $OVERSIZED -gt 0 ]; then
    echo "   Found $OVERSIZED oversized chunk(s), compressing..."
    
    for chunk in "$OUTPUT_DIR"/chunk_*.pdf; do
        chunk_size=$(wc -c < "$chunk")
        if [ $chunk_size -gt $MAX_SIZE_BYTES ]; then
            chunk_mb=$(echo $chunk_size | awk '{printf "%.2f", $1/1024/1024}')
            chunk_name=$(basename "$chunk")
            echo "   Compressing $chunk_name ($chunk_mb MB)..."
            
            # 压缩（使用 Ghostscript）
            gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/ebook \
               -dNOPAUSE -dQUIET -dBATCH \
               -sOutputFile="$chunk.compressed" \
               "$chunk" 2>/dev/null
            
            new_size=$(wc -c < "$chunk.compressed")
            new_mb=$(echo $new_size | awk '{printf "%.2f", $1/1024/1024}')
            
            if [ $new_size -lt $MAX_SIZE_BYTES ]; then
                mv "$chunk.compressed" "$chunk"
                echo "   ✅ Compressed to $new_mb MB"
            else
                # 更激进的压缩
                gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/screen \
                   -dNOPAUSE -dQUIET -dBATCH \
                   -sOutputFile="$chunk.compressed2" \
                   "$chunk" 2>/dev/null
                
                final_size=$(wc -c < "$chunk.compressed2")
                final_mb=$(echo $final_size | awk '{printf "%.2f", $1/1024/1024}')
                
                mv "$chunk.compressed2" "$chunk"
                rm -f "$chunk.compressed"
                echo "   ✅ Compressed to $final_mb MB (low quality)"
            fi
        fi
    done
else
    echo "   ✅ All chunks under 1MB limit"
fi

# Step 5: 清理
echo ""
if [ "$KEEP_PAGES" = true ]; then
    echo "Step 5: Keeping single pages in $TEMP_DIR"
    echo "   (for debugging)"
else
    echo "Step 5: Cleaning up temp files..."
    rm -rf "$TEMP_DIR"
fi

# 统计
CHUNK_COUNT=$(ls "$OUTPUT_DIR"/chunk_*.pdf 2>/dev/null | wc -l)
echo ""
echo "✅ Done! Created $CHUNK_COUNT chunks"
echo "   Output directory: $OUTPUT_DIR"