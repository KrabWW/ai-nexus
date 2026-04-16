#!/bin/bash
# AI Nexus Git Hooks 安装脚本
# 将 commit-msg 和 post-commit hooks 安装到当前 git 仓库
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
HOOKS_DIR="$PROJECT_DIR/.git/hooks"

if [ ! -d "$HOOKS_DIR" ]; then
    echo "错误：未找到 .git/hooks 目录，请在 git 仓库根目录运行"
    exit 1
fi

AI_NEXUS_URL="${AI_NEXUS_URL:-http://localhost:8000}"

# 检查 AI Nexus 服务是否可用
if ! curl -s --max-time 3 "${AI_NEXUS_URL}/health" > /dev/null 2>&1; then
    echo "警告：AI Nexus 服务未运行 (${AI_NEXUS_URL})"
    echo "      hooks 会在服务不可用时静默跳过"
fi

# 创建 commit-msg hook
cat > "$HOOKS_DIR/commit-msg" << 'HOOK_EOF'
#!/bin/bash
# AI Nexus Commit-Msg Hook
# 用户写完 commit message 后、提交前校验是否违反业务规则
# 使用 --no-verify 可跳过

COMMIT_MSG=$(cat "$1" 2>/dev/null)

if [ -z "$COMMIT_MSG" ]; then
    exit 0
fi

# 跳过 merge 提交
if echo "$COMMIT_MSG" | grep -q "^Merge "; then
    exit 0
fi

# 从 commit message 提取关键词（中英文分词）
KEYWORDS=$(echo "$COMMIT_MSG" | python3 -c "
import sys, re
msg = sys.stdin.read().strip()
# 1. 英文单词
en = re.findall(r'[a-zA-Z]{3,}', msg)
# 2. 中文: 按标点/空格分割后取每个片段
cn = []
for chunk in re.split(r'[，。、：；！？\s,.:;!?()（）\[\]【】]+', msg):
    if not re.search(r'[\u4e00-\u9fff]', chunk):
        continue
    chars = re.findall(r'[\u4e00-\u9fff]', chunk)
    for size in (4, 3, 2):
        for i in range(len(chars) - size + 1):
            w = ''.join(chars[i:i+size])
            if w not in cn:
                cn.append(w)
seen = set()
keywords = []
for w in cn + en:
    if w not in seen:
        seen.add(w)
        keywords.append(w)
print('\", \"'.join(keywords[:8]))
" 2>/dev/null)

# 获取仓库信息（用于绑定感知的规则过滤）
REPO_URL=$(git remote get-url origin 2>/dev/null || echo "")
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

# 调用 AI Nexus API 校验
AI_NEXUS_URL="${AI_NEXUS_URL:-http://localhost:8000}"
RESULT=$(curl -s --max-time 5 -X POST "${AI_NEXUS_URL}/api/hooks/pre-commit" \
  -H 'Content-Type: application/json' \
  -d "{\"change_description\": \"$COMMIT_MSG\", \"affected_entities\": [\"$KEYWORDS\"], \"repo_url\": \"$REPO_URL\", \"branch\": \"$BRANCH\"}" 2>/dev/null)

if [ -z "$RESULT" ]; then
    exit 0
fi

OUTPUT=$(echo "$RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    errors = data.get('errors', [])
    warnings = data.get('warnings', [])
    if errors or warnings:
        print('⚠️  业务规则校验:')
        for e in errors:
            print(f'  ✗ [{e[\"severity\"]}] {e[\"rule\"]}: {e[\"description\"][:80]}')
        for w in warnings:
            print(f'  ⚠ [{w[\"severity\"]}] {w[\"rule\"]}: {w[\"description\"][:80]}')
except:
    pass
" 2>/dev/null)

if [ -n "$OUTPUT" ]; then
    echo "" >&2
    echo "$OUTPUT" >&2
    echo "" >&2
    echo "请确认变更符合以上规则。使用 --no-verify 跳过校验。" >&2
fi

exit 0
HOOK_EOF

# 创建 post-commit hook
cat > "$HOOKS_DIR/post-commit" << 'HOOK_EOF'
#!/bin/bash
# AI Nexus Post-Commit Hook
# 提交后自动抽取业务知识，提交为待审核候选

COMMIT_MSG=$(git log -1 --pretty=format:"%s" 2>/dev/null)
COMMIT_BODY=$(git log -1 --pretty=format:"%b" 2>/dev/null)
DIFF_SUMMARY=$(git diff HEAD~1 --stat 2>/dev/null | tail -1)

if [ -z "$COMMIT_MSG" ]; then
    exit 0
fi

AI_NEXUS_URL="${AI_NEXUS_URL:-http://localhost:8000}"

RESULT=$(curl -s --max-time 15 -X POST "${AI_NEXUS_URL}/api/hooks/post-task" \
  -H 'Content-Type: application/json' \
  -d "{
    \"task_description\": \"$COMMIT_MSG\",
    \"change_summary\": \"$COMMIT_BODY\",
    \"diff\": \"$DIFF_SUMMARY\"
  }" 2>/dev/null)

if [ -z "$RESULT" ]; then
    exit 0
fi

SUBMITTED=$(echo "$RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if data.get('submitted'):
        cands = data.get('candidates', {})
        ents = len(cands.get('entities', []))
        rules = len(cands.get('rules', []))
        rels = len(cands.get('relations', []))
        audit_id = data.get('audit_id')
        if ents + rules + rels > 0:
            print(f'{ents}实体 + {rules}规则 + {rels}关系 → 审核ID:{audit_id}')
except:
    pass
" 2>/dev/null)

if [ -n "$SUBMITTED" ]; then
    echo "🧠 AI Nexus 自动抽取: $SUBMITTED"
    echo "   请在 ${AI_NEXUS_URL}/console/audit 审核"
fi

exit 0
HOOK_EOF

chmod +x "$HOOKS_DIR/commit-msg" "$HOOKS_DIR/post-commit"

echo "✅ Git Hooks 安装完成"
echo "   commit-msg  → 提交前校验业务规则"
echo "   post-commit → 提交后自动抽取知识"
echo ""
echo "使用 --no-verify 可跳过 commit-msg 校验"
echo "卸载: rm .git/hooks/commit-msg .git/hooks/post-commit"
