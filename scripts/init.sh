#!/bin/bash
# Multi-Agent Dispatcher 初始化脚本
# 用法: ./scripts/init.sh [--project-dir <path>]

set -e

PROJECT_DIR="${1:-.}"

# 解析参数
while [[ $# -gt 0 ]]; do
  case $1 in
    --project-dir)
      PROJECT_DIR="$2"
      shift 2
      ;;
    *)
      echo "未知参数: $1"
      exit 1
      ;;
  esac
done

DISPATCHER_DIR="$PROJECT_DIR/.dispatcher"

echo "初始化 Multi-Agent Dispatcher..."
echo "  项目目录: $PROJECT_DIR"
echo "  调度器目录: $DISPATCHER_DIR"

# 创建目录结构
mkdir -p "$DISPATCHER_DIR/SUMMARY"
mkdir -p "$DISPATCHER_DIR/CACHE"
mkdir -p "$DISPATCHER_DIR/LOGS"

# 如果 TASKS.json 不存在，创建默认模板
if [[ ! -f "$DISPATCHER_DIR/TASKS.json" ]]; then
  cat > "$DISPATCHER_DIR/TASKS.json" << 'EOF'
{
  "version": "1.0",
  "created_at": "TIMESTAMP",
  "updated_at": "TIMESTAMP",
  "scheduler": {
    "max_parallel": 3,
    "retry_policy": {
      "max_attempts": 3,
      "backoff_seconds": [5, 25, 125]
    }
  },
  "tasks": [],
  "file_locks": {},
  "health": {
    "last_check": "TIMESTAMP",
    "stuck_tasks": [],
    "context_usage": 0.0
  },
  "audit_log": []
}
EOF

  # 替换 TIMESTAMP 为实际时间
  TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  sed -i.bak "s/TIMESTAMP/$TIMESTAMP/g" "$DISPATCHER_DIR/TASKS.json"
  rm -f "$DISPATCHER_DIR/TASKS.json.bak"

  echo "  ✓ 创建 TASKS.json"
else
  echo "  ✓ TASKS.json 已存在，跳过"
fi

echo ""
echo "初始化完成！"
echo ""
echo "目录结构:"
echo "$DISPATCHER_DIR/"
echo "├── TASKS.json    # 任务状态机"
echo "├── SUMMARY/      # 子 agent 摘要"
echo "├── CACHE/        # 结果缓存"
echo "└── LOGS/         # 审计日志"
echo ""
echo "下一步:"
echo "  1. 编辑 TASKS.json 添加任务"
echo "  2. 使用 multi-agent-dispatcher skill 开始调度"
