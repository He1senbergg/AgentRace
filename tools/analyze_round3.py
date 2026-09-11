"""Generate the bounded round3 evidence report; no reconstruction of missing turns."""
from collections import Counter
import json
from pathlib import Path
from decode_match2 import decode

ROOT = Path(__file__).resolve().parents[1]
ROUNDS = (70, 131, 261, 331, 390)


def traces(path):
    result = {}
    for line_no, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        for tag in ('turn', 'trace_turn', 'shadow_turn'):
            marker = f'[{tag}] '
            if marker in line:
                row = json.loads(line.split(marker, 1)[1])
                result[tag, row['round']] = (line_no, row)
    return result


def enemy_snapshot(rows, turn):
    exact = [r for r in rows if r['round'] == turn]
    checkpoint = next((r['data'] for r in exact if r['kind'] == 'defense_checkpoint'), None)
    daily = next((r['data'] for r in exact if r['kind'] == 'defense_daily'), None)
    if not checkpoint and not daily:
        return ['unknown'] * 7
    d = checkpoint or daily
    if checkpoint:
        bases = [b['health'] for b in d['buildings'] if b['roleType'] == 'station']
        walls = [(str(b['id']), b['level'], b['health']) for b in d['buildings'] if b['roleType'] == 'wall' and b['health'] > 0]
        weapons = sorted([b['level'] for b in d['buildings'] if b['roleType'] in ('rocket', 'gatling', 'railgun')], reverse=True)
        actors = {str(a['id']): a['health'] for a in d['actors'] if a['health'] > 0}
        actor_text = f'{len(actors)} / {actors}'
    else:
        bases, weapons, actor_text = [d['base']], 'unknown', 'unknown'
        walls = ([(w[2], w[3], w[4]) for w in d['walls'] if w[4] > 0] if 'walls' in d else
                 [(str(w[:2]), 'unknown', w[2]) for w in d.get('walls_end', []) if w[2] > 0])
    return [str(bases), actor_text, str(weapons), f'{len(walls)} / {sum(w[2] for w in walls)}',
            str(dict(Counter(w[1] for w in walls))), str(d['gold']), str(d['score'])]


def generate():
    out = ['# Round3 实机证据与 V2.1 Shadow 修订', '',
           '三局实际响应均来自legacy；Shadow意图没有执行，不能把比赛失守归因于V2动作。', '',
           'MATCH2按run/event拼接全部分片，校验原文长度和SHA-256，再解压JSON。所有事件都解码；日志自己的log_omitted不是解码失败，缺失事件仍是unknown。',
           'defense_daily数组仅使用前五列x/y/id/level/HP，并与同回合defense_checkpoint交叉核对；其余未命名列不用于推导。墙HP总和不是战斗EHP或因果证明。',
           '下表严格取指定回合，不用R330冒充R331、R71冒充R70。score是日志累计总分，任务独立得分unknown；任务/升级事件另列。', '']
    for game in ('game8', 'game9', 'game10'):
        folder = ROOT / 'log/Versus/round3' / game
        enemy = next(folder.glob('enemy*'))
        ally = next(folder.glob('ally*'))
        rows, records = decode(enemy), traces(ally)
        counts = Counter(r['kind'] for r in rows)
        for row in rows:
            if row['kind'] == 'defense_daily':
                checkpoint = next((r['data'] for r in rows if r['round'] == row['round'] and r['kind'] == 'defense_checkpoint'), None)
                if checkpoint and 'walls' in row['data']:
                    a = {str(w['id']): (w['level'], w['health']) for w in checkpoint['buildings'] if w['roleType'] == 'wall' and w['health'] > 0}
                    b = {w[2]: (w[3], w[4]) for w in row['data']['walls'] if w[4] > 0}
                    if a != b:
                        raise ValueError('daily wall column interpretation failed cross-check')
        out += [f'## {game}', '', f'敌方源文件：`{enemy.relative_to(ROOT).as_posix()}`；完整校验解码 {len(rows)} 个事件。',
                f'事件计数：`{dict(counts)}`。', '',
                '| 阵营/回合 | station HP | actor count / HP | weapon levels | wall count / total HP | wall levels计数 | gold | total score |',
                '|---|---|---|---|---|---|---|---|']
        for turn in ROUNDS:
            out.append('| enemy R' + str(turn) + ' | ' + ' | '.join(enemy_snapshot(rows, turn)) + ' |')
            record = records.get(('shadow_turn', turn), (None, {}))[1]
            trace = records.get(('trace_turn', turn), (None, {}))[1]
            m = record.get('metrics', {})
            actor_hp = {str(a['id']): a['health'] for a in trace.get('roles', []) if a['kind'] in ('worker', 'pioneer')}
            out.append(f"| ally R{turn} | {m.get('station_hp', 'unknown')} | {m.get('actors_alive', 'unknown')} / {actor_hp or 'unknown'} | {m.get('weapon_levels', 'unknown')} | {m.get('walls', 'unknown')} / {sum(m['wall_hp']) if 'wall_hp' in m else 'unknown'} | unknown（摘要无墙level） | {m.get('gold', 'unknown')} | unknown |")
        out += ['', '敌方邻近检查点（与精确指定回合分开）：', '',
                '| 回合 | station HP | actor count / HP | weapon levels | wall count / total HP | wall levels计数 | gold | total score |',
                '|---|---|---|---|---|---|---|---|']
        for turn in (71, 200, 201, 330, 391):
            out.append('| R' + str(turn) + ' | ' + ' | '.join(enemy_snapshot(rows, turn)) + ' |')
        out += ['', '任务结束记录：下列score/gold是事件报告余额，不假定全由任务单独贡献。', '']
        for row in rows:
            if row['kind'] == 'task_end':
                d = row['data']
                out.append(f"- R{row['round']}：started={d.get('started', 'unknown')}，score={d.get('score', 'unknown')}，gold={d.get('gold', 'unknown')}，errors={d.get('errors', 'unknown')}。")
        out += ['', '升级结果记录（buy成功不等于已使用；未记录的后续事件为unknown）：', '']
        for row in rows:
            if row['kind'] == 'upgrade_result':
                d = row['data']
                out.append(f"- R{row['round']}：{d.get('action')} {d.get('name')}，result={d.get('result', 'unknown')}，gold={d.get('gold', 'unknown')}。")
        if game in ('game9', 'game10'):
            trace_line, trace = records['trace_turn', 331]
            _, turn = records['turn', 331]
            _, old_shadow = records['shadow_turn', 331]
            weapon_data = {w['id']: w for w in turn['weapons']}
            roles = []
            for r in trace['roles']:
                value = dict(id=r['id'], roleType=r['kind'], pos=dict(zip(('x', 'y'), r['pos'])), health=r['health'])
                if str(r['id']) in weapon_data:
                    w = weapon_data[str(r['id'])]
                    value.update(level=w['level'], cooldown=w['cooldown'], attackRange=w['range'])
                roles.append(value)
            fixture = dict(source=f'{ally.relative_to(ROOT).as_posix()}:{trace_line}', roundNo=331,
                           limitations='Partial diagnostic geometry only; missing walls/robots/inventory are not reconstructed. Fire targets are supplied by a test stub from actual legacy commands; no combat simulation.',
                           roles=roles, task_active=turn['task']['active'], legacy_actions=turn['actions'],
                           old_shadow_controllers=old_shadow['controllers'])
            dest = ROOT / 'tests/fixtures' / f'round3_{game}_r331.json'
            dest.parent.mkdir(exist_ok=True)
            dest.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        out.append('')
    (ROOT / 'docs/ROUND3_ANALYSIS.md').write_text('\n'.join(out) + '\n', encoding='utf-8')


if __name__ == '__main__':
    generate()
