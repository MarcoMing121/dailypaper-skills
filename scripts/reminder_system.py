#!/usr/bin/env python3
# scripts/reminder_system.py

import json
from datetime import datetime, timedelta
from pathlib import Path
from phase_manager import PhaseManager

class ReminderSystem:
    """阶段切换提醒系统"""
    
    def __init__(self):
        self.phase_manager = PhaseManager()
        self.reminder_file = Path("/tmp/last_reminder")
    
    def should_send_reminder(self) -> tuple:
        """检查是否应该发送提醒"""
        current_phase = self.phase_manager.get_current_phase()
        phase_config = self.phase_manager.PHASE_CONFIGS[current_phase]
        reminder_days = phase_config['reminder_days']
        
        if self.reminder_file.exists():
            with open(self.reminder_file, 'r') as f:
                last_reminder = datetime.fromisoformat(f.read().strip())
        else:
            last_reminder = datetime.min
        
        days_since_last = (datetime.now() - last_reminder).days
        
        for reminder_day in reminder_days:
            if days_since_last >= reminder_day:
                if last_reminder.date() != datetime.now().date():
                    return True, reminder_day
        
        return False, None
    
    def send_reminder(self, reminder_day: int):
        """发送提醒"""
        transition_check = self.phase_manager.check_phase_transition()
        
        print("📧 阶段提醒")
        print("="*60)
        print(f"阶段: {transition_check['current_phase_name']}")
        print(f"已运行: {transition_check['days_in_phase']} 天")
        print(f"建议: {transition_check['recommendation']}")
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
