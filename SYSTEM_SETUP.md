# Cron 任务管理 + 一键切换脚本

## 1. Cron 任务管理脚本

### 创建 cron_manager.py
```python
#!/usr/bin/env python3
# scripts/cron_manager.py

import subprocess
import json
from pathlib import Path
from phase_manager import PhaseManager

class CronManager:
    """管理cron任务"""
    
    def __init__(self):
        self.phase_manager = PhaseManager()
        self.cron_backup_dir = Path("/tmp/cron_backups")
        self.cron_backup_dir.mkdir(exist_ok=True)
    
    def backup_current_cron(self):
        """备份当前cron任务"""
        timestamp = subprocess.run(['date', '+%Y%m%d_%H%M%S'], 
                                 capture_output=True, text=True).stdout.strip()
        backup_file = self.cron_backup_dir / f"cron_backup_{timestamp}.txt"
        
        # 导出当前cron
        result = subprocess.run(['crontab', '-l'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            with open(backup_file, 'w') as f:
                f.write(result.stdout)
            print(f"✅ Cron任务已备份到: {backup_file}")
            return str(backup_file)
        else:
            print("⚠️ 没有现有cron任务或无法读取")
            return None
    
    def apply_phase_cron(self, phase_key: str = None):
        """应用指定阶段的cron任务"""
        if phase_key is None:
            phase_key = self.phase_manager.get_current_phase()
        
        # 备份当前cron
        self.backup_current_cron()
        
        # 生成新的cron任务
        self.phase_manager.generate_cron_tasks(phase_key)
        cron_file = Path("/tmp/current_phase_crontab")
        
        if not cron_file.exists():
            print("❌ Cron任务文件不存在")
            return False
        
        # 应用新的cron任务
        result = subprocess.run(['crontab', str(cron_file)], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ 已应用阶段 '{phase_key}' 的cron任务")
            
            # 显示即将执行的任务
            self.show_upcoming_tasks()
            return True
        else:
            print(f"❌ 应用cron任务失败: {result.stderr}")
            return False
    
    def show_upcoming_tasks(self):
        """显示即将执行的cron任务"""
        print("\n📋 当前计划的任务:")
        print("="*60)
        
        result = subprocess.run(['crontab', '-l'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            active_tasks = [line for line in lines if line.strip() and not line.startswith('#')]
            
            if active_tasks:
                for i, task in enumerate(active_tasks, 1):
                    print(f"{i}. {task}")
            else:
                print("没有活动的定时任务")
        
        print("="*60)
    
    def remove_all_tasks(self):
        """移除所有cron任务"""
        self.backup_current_cron()
        
        result = subprocess.run(['crontab', '-r'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ 已移除所有cron任务")
        else:
            print("⚠️ 没有cron任务需要移除或移除失败")
    
    def validate_cron_syntax(self):
        """验证cron语法"""
        result = subprocess.run(['crontab', '-l'], 
                              capture_output=True, text=True)
        
        if result.returncode != 0:
            print("⚠️ 没有cron任务")
            return True
        
        # 基本的cron语法检查
        lines = result.stdout.strip().split('\n')
        errors = []
        
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split()
            if len(parts) < 6:
                errors.append(f"第{i}行: 格式不正确 (字段数量不足)")
        
        if errors:
            print("❌ Cron语法错误:")
            for error in errors:
                print(f"  {error}")
            return False
        else:
            print("✅ Cron语法检查通过")
            return True

# CLI接口
if __name__ == "__main__":
    import sys
    
    cm = CronManager()
    
    if len(sys.argv) < 2:
        print("用法: python3 cron_manager.py [apply|backup|show|remove|validate]")
        print("  apply   - 应用当前阶段的cron任务")
        print("  backup  - 备份当前cron任务")
        print("  show    - 显示当前cron任务")
        print("  remove  - 移除所有cron任务")
        print("  validate- 验证cron语法")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "apply":
        phase_key = sys.argv[2] if len(sys.argv) > 2 else None
        cm.apply_phase_cron(phase_key)
    elif command == "backup":
        cm.backup_current_cron()
    elif command == "show":
        cm.show_upcoming_tasks()
    elif command == "remove":
        cm.remove_all_tasks()
    elif command == "validate":
        cm.validate_cron_syntax()
```

## 2. 一键切换脚本

### 创建 switch_phase.sh
```bash
#!/bin/bash

# 一键阶段切换脚本
# 用法: ./switch_phase.sh [phase_name]

set -e

echo "🎯 论文研究系统 - 阶段切换工具"
echo "======================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 检查Python脚本是否存在
PHASE_MANAGER="/root/.openclaw/workspace/dailypaper-skills/scripts/phase_manager.py"
CRON_MANAGER="/root/.openclaw/workspace/dailypaper-skills/scripts/cron_manager.py"

if [ ! -f "$PHASE_MANAGER" ]; then
    echo -e "${RED}❌ 错误: 找不到阶段管理器 ($PHASE_MANAGER)${NC}"
    exit 1
fi

if [ ! -f "$CRON_MANAGER" ]; then
    echo -e "${RED}❌ 错误: 找不到Cron管理器 ($CRON_MANAGER)${NC}"
    exit 1
fi

# 显示当前阶段
echo -e "${BLUE}📋 当前阶段信息:${NC}"
python3 "$PHASE_MANAGER" current

echo ""

# 如果没有参数，显示可用阶段
if [ $# -eq 0 ]; then
    echo -e "${YELLOW}可用阶段:${NC}"
    python3 "$PHASE_MANAGER" check | head -5
    echo ""
    echo "用法: $0 <phase_name>"
    echo "可用阶段: phase1_manual, phase2_smart, phase3_auto"
    echo ""
    echo "或者运行: $0 check - 检查是否应该切换阶段"
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
        
        # 应用新阶段的cron任务
        echo -e "${BLUE}🔄 应用新阶段cron任务:${NC}"
        python3 "$CRON_MANAGER" apply
        ;;
    "phase1_manual"|"phase2_smart"|"phase3_auto")
        echo -e "${YELLOW}🔄 切换到阶段: $COMMAND${NC}"
        
        # 确认切换
        echo -e "${RED}⚠️  这将改变系统配置和自动任务，继续吗? (y/N): ${NC}"
        read -r CONFIRM
        
        if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
            echo -e "${BLUE}❌ 取消切换${NC}"
            exit 0
        fi
        
        # 设置新阶段
        python3 "$PHASE_MANAGER" set "$COMMAND"
        
        # 应用新阶段的cron任务
        echo -e "${BLUE}🔄 应用新阶段cron任务:${NC}"
        python3 "$CRON_MANAGER" apply
        
        # 显示新阶段信息
        echo -e "${GREEN}✅ 阶段切换完成!${NC}"
        echo ""
        python3 "$PHASE_MANAGER" current
        ;;
    "backup-cron")
        echo -e "${BLUE}💾 备份cron任务:${NC}"
        python3 "$CRON_MANAGER" backup
        ;;
    "show-cron")
        echo -e "${BLUE}📋 当前cron任务:${NC}"
        python3 "$CRON_MANAGER" show
        ;;
    "remove-cron")
        echo -e "${RED}⚠️  移除所有cron任务? (y/N): ${NC}"
        read -r CONFIRM
        if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
            python3 "$CRON_MANAGER" remove
        else
            echo -e "${BLUE}❌ 取消操作${NC}"
        fi
        ;;
    *)
        echo -e "${RED}❌ 未知命令: $COMMAND${NC}"
        echo "可用命令: check, next, phase1_manual, phase2_smart, phase3_auto"
        echo "管理命令: backup-cron, show-cron, remove-cron"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}🎉 操作完成!${NC}"
```

## 3. 自动提醒系统

### 创建 reminder_system.py
```python
#!/usr/bin/env python3
# scripts/reminder_system.py

import smtplib
import json
from datetime import datetime, timedelta
from pathlib import Path
from phase_manager import PhaseManager
from email.mime.text import MIMEText

class ReminderSystem:
    """阶段切换提醒系统"""
    
    def __init__(self):
        self.phase_manager = PhaseManager()
        self.reminder_file = Path("/tmp/last_reminder")
    
    def should_send_reminder(self) -> bool:
        """检查是否应该发送提醒"""
        current_phase = self.phase_manager.get_current_phase()
        phase_config = self.phase_manager.PHASE_CONFIGS[current_phase]
        reminder_days = phase_config['reminder_days']
        
        # 检查上次提醒时间
        if self.reminder_file.exists():
            with open(self.reminder_file, 'r') as f:
                last_reminder = datetime.fromisoformat(f.read().strip())
        else:
            last_reminder = datetime.min
        
        # 检查是否到了提醒间隔
        days_since_last = (datetime.now() - last_reminder).days
        
        for reminder_day in reminder_days:
            if days_since_last >= reminder_day:
                # 检查是否在同一天已经提醒过
                if last_reminder.date() != datetime.now().date():
                    return True, reminder_day
        
        return False, None
    
    def send_reminder(self, reminder_day: int):
        """发送提醒"""
        transition_check = self.phase_manager.check_phase_transition()
        
        subject = f"🎯 论文研究系统 - {transition_check['current_phase_name']} 阶段提醒"
        
        body = f"""
您好!

您的论文研究系统已运行 {transition_check['days_in_phase']} 天，
当前处于 "{transition_check['current_phase_name']}" 阶段。

📊 当前统计:
- 总论文数: {transition_check['stats']['total_papers']}
- 总概念数: {transition_check['stats']['total_concepts']}
- 近30天新增: {transition_check['stats']['recent_papers_30_days']} 篇

💡 系统建议:
{transition_check['recommendation']}

🔄 快速切换命令:
```bash
cd /root/.openclaw/workspace/dailypaper-skills
./scripts/switch_phase.sh check    # 检查是否该切换
./scripts/switch_phase.sh next     # 切换到下一阶段
./scripts/switch_phase.sh phase2_smart  # 切换到智能阶段
```

📅 下次提醒: {reminder_day} 天后

祝您研究顺利!
论文研究系统
        """
        
        # 这里可以集成邮件、Slack、微信等通知方式
        print("📧 提醒内容:")
        print("="*60)
        print(subject)
        print(body)
        print("="*60)
        
        # 保存提醒时间
        with open(self.reminder_file, 'w') as f:
            f.write(datetime.now().isoformat())
        
        print("✅ 提醒已记录")
    
    def daily_check(self):
        """每日检查并发送提醒"""
        should_remind, reminder_day = self.should_send_reminder()
        
        if should_remind:
            self.send_reminder(reminder_day)
        else:
            print("📅 今日无需提醒")

if __name__ == "__main__":
    rs = ReminderSystem()
    rs.daily_check()
```

## 4. 初始化脚本

### 创建 init_system.sh
```bash
#!/bin/bash

# 系统初始化脚本
echo "🚀 初始化论文研究系统"
echo "========================"

# 设置执行权限
chmod +x /root/.openclaw/workspace/dailypaper-skills/scripts/switch_phase.sh
chmod +x /root/.openclaw/workspace/dailypaper-skills/scripts/cron_manager.py
chmod +x /root/.openclaw/workspace/dailypaper-skills/scripts/phase_manager.py
chmod +x /root/.openclaw/workspace/dailypaper-skills/scripts/reminder_system.py

echo "✅ 脚本权限设置完成"

# 设置初始阶段
echo -e "\n🎯 设置初始阶段为 phase1_manual"
python3 /root/.openclaw/workspace/dailypaper-skills/scripts/phase_manager.py set phase1_manual

# 应用初始cron配置
echo -e "\n🔄 应用初始cron配置"
python3 /root/.openclaw/workspace/dailypaper-skills/scripts/cron_manager.py apply

# 创建每日提醒cron
echo -e "\n⏰ 设置每日提醒 (每天上午8点)"
echo "0 8 * * * cd /root/.openclaw/workspace/dailypaper-skills && python3 scripts/reminder_system.py" | crontab -

echo -e "\n🎉 系统初始化完成!"
echo ""
echo "📋 快速开始:"
echo "  ./scripts/switch_phase.sh check     # 检查阶段状态"
echo "  ./scripts/switch_phase.sh next      # 切换到下一阶段"
echo "  ./scripts/switch_phase.sh show-cron # 查看当前任务"
echo ""
echo "📚 当前阶段: 集中阅读期 (phase1_manual)"
echo "   手动深度阅读，基础概念建设"
```

## 5. 使用说明

### 立即部署命令:
```bash
# 1. 运行初始化脚本
cd /root/.openclaw/workspace/dailypaper-skills
./scripts/init_system.sh

# 2. 检查当前状态
./scripts/switch_phase.sh check

# 3. 查看当前cron任务
./scripts/switch_phase.sh show-cron
```

### 日常使用:
```bash
# 检查是否该切换阶段
./scripts/switch_phase.sh check

# 切换到下一阶段
./scripts/switch_phase.sh next

# 手动切换到指定阶段
./scripts/switch_phase.sh phase2_smart

# 查看当前阶段
./scripts/switch_phase.sh current
```

### 阶段切换时自动完成:
- ✅ 更新系统配置
- ✅ 生成对应cron任务
- ✅ 备份旧配置
- ✅ 显示新任务计划
- ✅ 设置提醒系统

**现在你有了完整的分阶段基础设施！切换阶段只需要一条命令，所有配置自动更新。** 🎯