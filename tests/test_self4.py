"""Measured Self/4 failures; synthetic states do not simulate official combat."""
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from src import main3 as main
from test_actions import role, state, zone, validator
from test_tasks import task_state

class Self4Tests(unittest.TestCase):
    def test_discovery_reads_nested_task_and_api_once_and_keeps_material(self):
        with tempfile.TemporaryDirectory() as directory:
            nested=Path(directory)/'nested'; nested.mkdir()
            (nested/'task_1_beijing.md').write_text('Use API_DOCS.md; answer from evidence',encoding='utf-8')
            (nested/'API_DOCS.md').write_text('Local task API documentation',encoding='utf-8')
            session=main.GameSession(origin=1)
            data=task_state(1,'请阅读task_1_beijing.md，获取任务信息')
            first=session.handle(data)
            self.assertFalse(first['prompt'])
            self.assertEqual(first,session.handle(data))
            script=shlex.split(first['executeCmd'])[2]
            result=subprocess.run([sys.executable,'-B','-c',script],cwd=directory,capture_output=True,text=True,encoding='utf-8',timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            documents=json.loads(result.stdout)['documents']
            self.assertEqual({Path(d['path']).name for d in documents},{'task_1_beijing.md','API_DOCS.md'})
            data['roundNo']=2; data['lastCmdResult']='[exitCode:0]\n'+result.stdout
            response=session.handle(data)
            self.assertIn('Local task API documentation',response['prompt'])
            self.assertFalse(response['executeCmd'])
            self.assertIn('Local task API documentation',session.memory.task['documents'])

    def test_discovery_timeout_falls_back_to_llm_without_repeating(self):
        session=main.GameSession(origin=1)
        session.handle(task_state(1,'Read missing_task.md'))
        data=task_state(2,'Read missing_task.md'); data['lastCmdResult']='[TIMEOUT]\npartial'
        response=session.handle(data)
        self.assertTrue(response['prompt']);self.assertFalse(response['executeCmd'])
        self.assertIn('[TIMEOUT]',response['prompt'])

    def test_far_vendor_does_not_trigger_four_item_cross_map_delivery(self):
        data=state(role(1,'worker',5,5),vendorShopList=[dict(name='copper',price=5)])
        data['teamOur']['goldNum']=0;data['teamOur']['roles'][0]['backpack']=['copper']*4
        zone(data,'copper',6,5);zone(data,'vendor',20,5)
        v=validator(data);main.EconomyPlanner(v).workers()
        self.assertEqual(v.commands['1']['action'],'collect')

    def test_default_construction_uses_group_damage_weapon(self):
        data=state(role(1,'worker',9,11),role(2,'station',10,10,level=1))
        built=0
        for _ in range(12):
            v=validator(data);main.DefensePlanner(v).construct()
            command=v.commands['1']
            if command['action']=='move':
                data['teamOur']['roles'][0]['pos']=command['targetPos'][0]
                continue
            self.assertEqual(command['name'],'rocket')
            p=command['targetPos'][0]
            data['teamOur']['roles'].append(role(20+built,'rocket',p['x'],p['y'],level=1))
            data['teamOur']['goldNum']-=25;built+=1
            if built==3:break
        self.assertEqual(built,3)

    def test_healthy_base_does_not_preempt_rocket_upgrade(self):
        data=state(role(1,'worker',9,10),role(2,'station',10,10,level=1),role(3,'rocket',9,9,level=1),role(4,'rocket',8,9,level=1),weaponShopList=[dict(name='WeaponUpgradeVoucher1',price=100),dict(name='StationUpgradeVoucher1',price=100)])
        data['teamOur']['roles'][1]['health']=1500
        data['teamOur']['goldNum']=100;zone(data,'weaponShop',8,10)
        v=validator(data);main.DefensePlanner(v).maintain()
        self.assertEqual(v.commands['1']['name'],'WeaponUpgradeVoucher1')

    def test_group_firepower_on_distant_cluster_exceeds_mixed_level_one(self):
        def volley(kinds):
            data=state(role(1,'worker',8,11),role(2,'worker',11,12),role(3,'pioneer',12,9))
            for i,(kind,cell) in enumerate(zip(kinds,[(9,11),(11,11),(12,10)])):
                data['teamOur']['roles'].append(role(10+i,kind,*cell,level=1))
            data['robot']=[dict(id=100+i,roleType='smallRobot',pos=dict(x=17+i%3,y=10+i//3),health=40,targetTeam='challenger') for i in range(9)]
            v=validator(data,main.Phase(1,71));d=main.DefensePlanner(v);d.fire()
            return 360-sum(d.remaining.values())
        mixed=volley(['gatling','rocket','railgun'])
        rockets=volley(['rocket']*3)
        self.assertGreaterEqual(rockets,2*mixed)
        self.assertGreater(mixed,0)

    def test_discovery_serialized_output_bounded_and_task_root_prioritized(self):
        with tempfile.TemporaryDirectory() as directory:
            cwd=Path(directory)/'cwd';cwd.mkdir()
            for n in range(605):(cwd/str(n)).mkdir()
            root=Path(directory)/'tasks';root.mkdir()
            (root/'task_data.md').write_bytes(b'\x01'*16000)
            (root/'API_DOCS.md').write_bytes(b'\x02'*16000)
            script=shlex.split(main.task_discovery_command('Read task_data.md'))[2]
            script=script.replace("'/tmp/selfEvolutionTask'",repr(str(root)))
            result=subprocess.run([sys.executable,'-B','-c',script],cwd=cwd,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertLessEqual(len(result.stdout),48002)
            payload=json.loads(result.stdout)
            self.assertTrue(payload['documents'])
            self.assertEqual(Path(payload['documents'][0]['path']).name,'task_data.md')
            self.assertTrue(payload['output_limited'])
