export const TRACK_LABEL = { read: '입모양 읽기', speak: '말하기', listen: '소리 듣기' }
export const trackLabel = (value) => ({ 독화: '입모양 읽기', 발화: '말하기', 듣기: '소리 듣기' }[value] || value)
export const taskLabel = (task) => task.key === 'read_once' ? '입모양 읽기 1회' : task.label
