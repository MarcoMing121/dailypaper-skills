#!/usr/bin/env python3
# scripts/phase_manager.py

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

class PhaseManager:
    """管理不同阶段配置"""
    
    PHASE_CONFIGS = {
        'phase1_manual': {
            'name': '集中阅读期',
            'description': '手动深度阅读，基础概念建设',
            'config': {
                'AUTO_UPDATE_CONCEPTS': False,
                'UPDATE_MODE': 'manual',
                'MIN_NEW_PAPERS_TRIGGER': 999,
                'MAX_DAYS_BETWEEN_RUNS': 999,
                'PREVIEW_BEFORE_UPDATE': True,
                'BACKUP_BEFORE_UPDATE': False,
                'DAILY_AUTO_TASKS': False
            },
            'cron_schedule': {
                'concept_weaver': None,
                'generate_mocs': None,
                'smart_trigger': None
            },
            'reminder_days': [7, 14, 30],
            'next_phase_check': 30
        },
        
        'phase2_smart': {
            'name': '关联发现期', 
            'description': '智能触发，增量更新，定期深度整理',
            'config': {
                'AUTO_UPDATE_CONCEPTS': True,
                'UPDATE_MODE': 'smart',
                'MIN_NEW_PAPERS_TRIGGER': 5,
                'MAX_DAYS_BETWEEN_RUNS': 10,
                'PREVIEW_BEFORE_UPDATE': True,
                'BACKUP_BEFORE_UPDATE': True,
                'DAILY_AUTO_TASKS': False
            },
            'cron_schedule': {
                'smart_trigger': '0 9 * * *',
                'concept_weaver_incremental': '0 10 * * 1,4',
                'generate_mocs': '0 11 * * 5',
                'deep_analysis': '0 14 1 * *'
            },
            'reminder_days': [15, 45, 90],
            'next_phase_check': 90
        },
        
        'phase3_auto': {
            'name': '知识整合期',
            'description': '定时维护，季度深度重构，跨领域关联发现',
            'config': {
                'AUTO_UPDATE_CONCEPTS': True,
                'UPDATE_MODE': 'auto', 
                'MIN_NEW_PAPERS_TRIGGER': 3,
                'MAX_DAYS_BETWEEN_RUNS': 7,
                'PREVIEW_BEFORE_UPDATE': False,
                'BACKUP_BEFORE_UPDATE': True,
                'DAILY_AUTO_TASKS': True
            },
            'cron_schedule': {
                'smart_trigger': '0 8 * * *',
                'concept_weaver_auto': '0 9 * * *',
                'generate_mocs': '0 10 * * *',
                'cross_domain_analysis': '0 15 1 * *',
                'quarterly_deep': '0 16 1 */3 *'
            },
            'reminder_days': [30, 60, 120],
            'next_phase_check': 180
        }
    }
    
    def __init__(self, config_file: str = "/root/.openclaw/workspace/dailypaper-skills/_shared/user-config.json"):
        self.config_file = Path(config_file)
        self.current_phase_file = Path("/tmp/current_phase")
        
    def get_current_phase(self) -> str:
        if self.current_phase_file.exists():
            with open(self.current_phase_file, 'r') as f:
                return f.read().strip()
        else:
            self.set_phase('phase1_manual')
            return 'phase1_manual'
    
    def set_phase(self, phase_key: str):
        if phase_key not in self.PHASE_CONFIGS:
            raise ValueError(f"未知阶段: {phase_key}")
        
        config = self.load_user_config()
        phase_config = self.PHASE_CONFIGS[phase_key]['config']
        
        config.update(phase_config)
        config['PHASE'] = phase_key
        config['PHASE_START_DATE'] = datetime.now().isoformat()
        
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        with open(self.current_phase_file, 'w') as f:
            f.write(phase_key)
        
        print(f"✅ 已切换到阶段: {self.PHASE_CONFIGS[phase_key]['name']}")
        
        self.generate_cron_tasks(phase_key)
        return phase_key
    
    def load_user_config(self) -> dict:
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                return json.load(f)
        else:
            return {}
    
    def generate_cron_tasks(self, phase_key: str):
        phase_config = self.PHASE_CONFIGS[phase_key]
        cron_schedule = phase_config['cron_schedule']
        
        cron_file = Path("/tmp/current_phase_crontab")
        
        with open(cron_file, 'w') as f:
            f.write("# Auto-generated cron tasks for phase: " + phase_key + "\n")
            f.write("# Generated at: " + datetime.now().isoformat() + "\n\n")
            
            for task_name, schedule in cron_schedule.items():
                if schedule is None:
                    continue
                    
                if task_name == 'smart_trigger':
                    cmd = f"cd /root/.openclaw/workspace/dailypaper-skills && python3 scripts/smart_trigger.py"
                elif task_name == 'concept_weaver_incremental':
                    cmd = f"cd /root/.openclaw/workspace/dailypaper-skills && python3 skills/concept-weaver/scripts/weave_concepts.py --notes-dir \"/root/.openclaw/workspace/ObsidianVault/论文笔记\" --update-mode incremental"
                elif task_name == 'concept_weaver_auto':
                    cmd = f"cd /root/.openclaw/workspace/dailypaper-skills && python3 skills/concept-weaver/scripts/weave_concepts.py --notes-dir \"/root/.openclaw/workspace/ObsidianVault/论文笔记\" --update-mode auto"
                elif task_name == 'generate_mocs':
                    cmd = f"cd /root/.openclaw/workspace/dailypaper-skills && python3 skills/generate-mocs/SKILL.py"
                elif task_name == 'deep_analysis':
                    cmd = f"cd /root/.openclaw/workspace/dailypaper-skills && python3 skills/concept-weaver/scripts/weave_concepts.py --notes-dir \"/root/.openclaw/workspace/ObsidianVault/论文笔记\" --update-mode full"
                else:
                    continue
                
                f.write(f"{schedule} {cmd}\n")
        
        print(f"📋 Cron任务已生成: {cron_file}")
    
    def check_phase_transition(self) -> dict:
        current_phase = self.get_current_phase()
        phase_config = self.PHASE_CONFIGS[current_phase]
        
        config = self.load_user_config()
        start_date_str = config.get('PHASE_START_DATE')
        
        if not start_date_str:
            return {'should_transition': False, 'reason': 'No start date recorded'}
        
        start_date = datetime.fromisoformat(start_date_str)
        days_in_phase = (datetime.now() - start_date).days
        
        should_transition = days_in_phase >= phase_config['next_phase_check']
        
        return {
            'should_transition': should_transition,
            'days_in_phase': days_in_phase,
            'next_check_days': phase_config['next_phase_check'],
            'current_phase': current_phase,
            'current_phase_name': phase_config['name'],
            'recommendation': self.get_transition_recommendation(current_phase, days_in_phase)
        }
    
    def get_transition_recommendation(self, current_phase: str, days_in_phase: int) -> str:
        config = self.PHASE_CONFIGS[current_phase]
        
        if days_in_phase >= config['next_phase_check']:
            return f"🎓 建议进入下一阶段：已进行{days_in_phase}天，超过建议时长{config['next_phase_check']}天"
        else:
            return f"📚 继续当前阶段：还需{config['next_phase_check'] - days_in_phase}天"

if __name__ == "__main__":
    import sys
    pm = PhaseManager()
    
    if len(sys.argv) < 2:
        print("用法: python3 phase_manager.py [current|set|check|next]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "current":
        phase = pm.get_current_phase()
        config = pm.PHASE_CONFIGS[phase]
        print(f"当前阶段: {config['name']} ({phase})")
    elif command == "set":
        pm.set_phase(sys.argv[2])
    elif command == "check":
        result = pm.check_phase_transition()
        print("阶段转换检查:", result)
    elif command == "next":
        current = pm.get_current_phase()
        phases = list(pm.PHASE_CONFIGS.keys())
        current_idx = phases.index(current)
        if current_idx < len(phases) - 1:
            pm.set_phase(phases[current_idx + 1])
