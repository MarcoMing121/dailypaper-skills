#!/bin/bash
# extract_images.sh
# 从 MinerU 提取结果中复制图片到 assets，并验证

set -e

# 参数
MINERU_DIR="$1"        # MinerU 输出目录（包含 chunk 子目录）
ASSETS_DIR="$2"        # 目标 assets 目录
NOTE_FILE="$3"         # 笔记文件（用于提取引用的图片）

# 验证参数
if [ -z "$MINERU_DIR" ] || [ -z "$ASSETS_DIR" ]; then
    echo "Usage: $0 <mineru_dir> <assets_dir> [note_file]"
    echo ""
    echo "Example:"
    echo "  $0 /tmp/paper_mineru /path/to/assets/PaperName /path/to/note.md"
    exit 1
fi

echo "📥 Extracting images from MinerU..."
echo "   Source: $MINERU_DIR"
echo "   Target: $ASSETS_DIR"

# Step 1: 统计源图片数量
TOTAL_IMAGES=$(find "$MINERU_DIR" -path "*/images/*.jpg" -type f 2>/dev/null | wc -l)
echo ""
echo "📊 Found $TOTAL_IMAGES images in MinerU output"

if [ "$TOTAL_IMAGES" -eq 0 ]; then
    echo "⚠️  No images found! Check MinerU extraction."
    exit 1
fi

# Step 2: 创建目标目录
mkdir -p "$ASSETS_DIR"

# Step 3: 如果提供了笔记文件，只复制引用的图片
if [ -n "$NOTE_FILE" ] && [ -f "$NOTE_FILE" ]; then
    echo ""
    echo "📝 Checking referenced images in note..."
    
    # 提取笔记中引用的图片（支持两种格式）
    # 1. ![[../assets/PaperName/xxx.jpg]]
    # 2. ![[xxx.jpg]]
    REFERENCED=$(grep -oP '!\[\[[^\]]*\.jpg\]\]' "$NOTE_FILE" | \
                 sed 's/!\[\[//; s/\]\]//; s/.*\///' | sort -u)
    
    if [ -z "$REFERENCED" ]; then
        echo "⚠️  No image references found in note, copying all images..."
        find "$MINERU_DIR" -path "*/images/*.jpg" -type f -exec cp {} "$ASSETS_DIR/" \;
    else
        echo "   Referenced images: $(echo "$REFERENCED" | wc -l)"
        
        COPIED=0
        for img in $REFERENCED; do
            # 在 MinerU 输出中查找
            FOUND=$(find "$MINERU_DIR" -name "$img" -type f 2>/dev/null | head -1)
            if [ -n "$FOUND" ]; then
                cp "$FOUND" "$ASSETS_DIR/"
                COPIED=$((COPIED + 1))
            else
                echo "   ⚠️  Not found: $img"
            fi
        done
        
        echo ""
        echo "✅ Copied $COPIED referenced images"
    fi
else
    # 没有笔记文件，复制所有图片
    echo ""
    echo "📦 Copying all images..."
    find "$MINERU_DIR" -path "*/images/*.jpg" -type f -exec cp {} "$ASSETS_DIR/" \;
fi

# Step 4: 验证
COPIED_COUNT=$(ls "$ASSETS_DIR"/*.jpg 2>/dev/null | wc -l)
echo ""
echo "📊 Summary:"
echo "   MinerU extracted: $TOTAL_IMAGES images"
echo "   Copied to assets: $COPIED_COUNT images"

if [ "$COPIED_COUNT" -eq 0 ]; then
    echo ""
    echo "❌ ERROR: No images were copied!"
    echo "   Check if MinerU extraction was successful."
    exit 1
fi

# Step 5: 只有在验证成功后才删除临时目录（可选）
# 默认不删除，保留备份
echo ""
echo "✅ Image extraction complete!"
echo "   Assets directory: $ASSETS_DIR"
echo ""
echo "💡 To clean up MinerU temp directory:"
echo "   rm -rf $MINERU_DIR"