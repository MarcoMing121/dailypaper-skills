#!/bin/bash

# 一键阶段切换脚本
set -e

echo "🎯 论文研究系统 - 阶段切换工具"
echo "======================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 脚本路径
PHASE_MANAGER="/root/.openclaw/workspace/dailypaper-skills/scripts/phase_manager.py"
CRON_MANAGER="/root/.openclaw/workspace/dailypaper-skills/scripts/cron_manager.py"

if [ ! -f "$PHASE_MANAGER" ] || [ ! -f "$CRON_MANAGER" ]; then
    echo -e "${RED}❌ 错误: 找不到必要的脚本文件${NC}"
    exit 1
fi

# 显示当前阶段
echo -e "${BLUE}📋 当前阶段信息:${NC}"
python3 "$PHASE_MANAGER" current

echo ""

# 如果没有参数，显示用法
if [ $# -eq 0 ]; then
    echo -e "${YELLOW}用法: $0 <command>${NC}"
    echo "可用命令:"
    echo "  check              - 检查是否应该切换阶段"
    echo "  next               - 切换到下一阶段"
    echo "  phase1_manual      - 切换到阶段1 (集中阅读期)"
    echo "  phase2_smart       - 切换到阶段2 (关联发现期)"
    echo "  phase3_auto        - 切换到阶段3 (知识整合期)"
    echo "  show-cron          - 显示当前cron任务"
    echo "  backup-cron        - 备份cron任务"
    exit 0
fi

COMMAND=$1

case $COMMAND in
    "check")
        echo -e "${BLUE}🔍 阶段转换检查:${NC}"
        python3 "$PHASE_MANAGER" check
        ;;
    "next")
        echo -e "${YELLOW}⏭️  切换到下一阶段:${NC}"
        python3 "$PHASE_MANAGER" next
        echo -e "${BLUE}🔄 应用新阶段cron任务:${NC}"
        python3 "$CRON_MANAGER" apply
        echo -e "${GREEN}✅ 阶段切换完成!${NC}"
        python3 "$PHASE_MANAGER" current
        ;;
    "phase1_manual"|"phase2_smart"|"phase3_auto")
        echo -e "${YELLOW}🔄 切换到阶段: $COMMAND${NC}"
        echo -e "${RED}⚠️  这将改变系统配置，继续吗? (y/N): ${NC}"
        read -r CONFIRM
        
        if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
            echo -e "${BLUE}❌ 取消切换${NC}"
            exit 0
        fi
        
        python3 "$PHASE_MANAGER" set "$COMMAND"
        echo -e "${BLUE}🔄 应用新阶段cron任务:${NC}"
        python3 "$CRON_MANAGER" apply
        
        echo -e "${GREEN}✅ 阶段切换完成!${NC}"
        echo ""
        python3 "$PHASE_MANAGER" current
        ;;
    "show-cron")
        echo -e "${BLUE}📋 当前cron任务:${NC}"
        python3 "$CRON_MANAGER" show
        ;;
    "backup-cron")
        echo -e "${BLUE}💾 备份cron任务:${NC}"
        python3 "$CRON_MANAGER" backup
        ;;
    *)
        echo -e "${RED}❌ 未知命令: $COMMAND${NC}"
        exit 1
        ;;
esac

echo ""
