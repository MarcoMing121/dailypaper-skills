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
        
        result = subprocess.run(['crontab', '-l'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            with open(backup_file, 'w') as f:
                f.write(result.stdout)
            print(f"✅ Cron任务已备份到: {backup_file}")
            return str(backup_file)
        else:
            print("⚠️ 没有现有cron任务")
            return None
    
    def apply_phase_cron(self, phase_key: str = None):
        """应用指定阶段的cron任务"""
        if phase_key is None:
            phase_key = self.phase_manager.get_current_phase()
        
        self.backup_current_cron()
        self.phase_manager.generate_cron_tasks(phase_key)
        cron_file = Path("/tmp/current_phase_crontab")
        
        if not cron_file.exists():
            print("❌ Cron任务文件不存在")
            return False
        
        result = subprocess.run(['crontab', str(cron_file)], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ 已应用阶段 '{phase_key}' 的cron任务")
            self.show_upcoming_tasks()
            return True
        else:
            print(f"❌ 应用cron任务失败")
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
        subprocess.run(['crontab', '-r'], capture_output=True)
        print("✅ 已移除所有cron任务")
    
    def validate_cron_syntax(self):
        """验证cron语法"""
        result = subprocess.run(['crontab', '-l'], 
                              capture_output=True, text=True)
        
        if result.returncode != 0:
            print("⚠️ 没有cron任务")
            return True
        
        lines = result.stdout.strip().split('\n')
        errors = []
        
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split()
            if len(parts) < 6:
                errors.append(f"第{i}行: 格式不正确")
        
        if errors:
            print("❌ Cron语法错误:")
            for error in errors:
                print(f"  {error}")
            return False
        else:
            print("✅ Cron语法检查通过")
            return True

if __name__ == "__main__":
    import sys
    cm = CronManager()
    
    if len(sys.argv) < 2:
        print("用法: python3 cron_manager.py [apply|backup|show|remove|validate]")
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
