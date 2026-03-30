#!/bin/bash

# 系统初始化脚本
echo "🚀 初始化论文研究系统"
echo "========================"

# 设置执行权限
echo "📝 设置脚本权限..."
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
echo ""
echo "🔧 系统组件已就绪:"
echo "  ✅ Concept-Weaver 增量更新"
echo "  ✅ 智能触发脚本"
echo "  ✅ 阶段管理系统"
echo "  ✅ Cron任务管理"
echo "  ✅ 自动提醒系统"
