# Weizhi Crontask

一个基于 FastAPI + APScheduler 的内网定时任务调度服务，支持任务持久化（MongoDB），提供简单的 HTTP 接口供其它系统创建/删除任务。任务执行方式为请求一个 URL（未来可扩展其它类型）。

## 功能特性

- 基于 Cron 表达式的任务调度
- MongoDB 持久化存储，重启不丢任务
- 任务 ID 全局唯一（由客户端指定）
- 通过 HTTP API 创建/删除任务
- 任务执行：定时请求指定 URL
- Docker 部署，适合内网环境
- 无需安全认证（内网使用）

## 运行原理（简述）

- 任务创建后写入 MongoDB
- APScheduler 从 MongoDB 读取并调度执行
- 到点后发起 HTTP 请求调用目标 URL
- 任务删除后从 MongoDB 和调度器中移除

## 依赖

- Python 3.10+
- MongoDB 4.4+
- Docker / Docker Compose（部署用）

## 快速开始

### 1. 本地运行（开发）

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

启动服务：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8800
```

### 2. Docker 部署（不依赖 Compose）

构建镜像：

```bash
docker build -t weizhi-crontask:latest .
```

准备环境变量文件（不提交）：

```bash
cp .env.example .env
# 编辑 .env，填写你的 MONGO_URI 等
```

运行容器：

```bash
docker run -d \
  -p 8800:8800 \
  --restart always \
  --env-file .env \
  --name weizhi-crontask \
  --network rqk-net \
  weizhi-crontask:latest
```

## API 设计（当前实现）

### 创建任务

`POST /jobs`

```json
{
  "id": "job-ping-001",
  "cron": "*/10 * * * * *",
  "url": "http://127.0.0.1:8000",
  "method": "POST",
  "headers": {
    "Content-Type": "application/json",
    "X-Trace-Id": "demo-001"
  },
  "body": "{\"ping\":\"hello\"}"
}
```

返回：

```json
{
  "id": "job-ping-001",
  "status": "scheduled"
}
```

### 删除任务

`DELETE /jobs/{id}`

返回：

```json
{
  "id": "job-ping-001",
  "status": "deleted"
}
```

### 查询任务

`GET /jobs/{id}`

```json
{
  "id": "job-demo-001",
  "cron": "*/5 * * * *",
  "url": "http://example.internal/api/ping",
  "method": "GET",
  "headers": null,
  "body": null,
  "next_run_time": "2024-01-01T12:00:00+08:00",
  "status": "scheduled"
}
```

### 查询任务执行记录（分页）

`GET /jobs/{id}/runs?limit=20&offset=0`

```json
{
  "total": 12,
  "limit": 20,
  "offset": 0,
  "items": [
    {
      "job_id": "job-demo-001",
      "url": "http://example.internal/api/ping",
      "cron": "*/5 * * * *",
      "method": "GET",
      "status_code": 200,
      "ok": true,
      "response_text": "ok",
      "elapsed_ms": 12.3,
      "error": null,
      "run_at": "2024-01-01T04:00:00+00:00"
    }
  ]
}
```

### 健康检查

`GET /health`

```json
{
  "status": "ok"
}
```

## Demo（使用示例）

下面是一个创建任务并触发的示例流程：

```bash
# 创建任务：每 5 分钟请求一次
curl -X POST http://localhost:8800/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "job-ping-001",
    "cron": "*/10 * * * * *",
    "url": "http://127.0.0.1:8000",
    "method": "POST",
    "headers": {
      "Content-Type": "application/json",
      "X-Trace-Id": "demo-001"
    },
    "body": "{\"ping\":\"hello\"}"
  }'

# 删除任务
curl -X DELETE http://localhost:8800/jobs/job-ping-001
```

你也可以在项目中实现一个 `GET /demo/target` 接口，方便展示调度效果。

## 任务唯一性

- 任务 ID 由调用方传入，必须全局唯一
- 若 ID 已存在，应返回错误或覆盖策略（建议返回 409）

## Cron 表达式

- 标准 5 段格式：`分 时 日 月 周`
- 也支持 6 段（含秒）：`秒 分 时 日 月 周`
- 例：`*/10 * * * * *` 表示每 10 秒执行一次

## 配置建议

环境变量（可选）：

- `MONGO_URI`：MongoDB 连接串，默认 `mongodb://mongo:27017`
- `MONGO_DB`：数据库名，默认 `weizhi_crontask`
- `JOBSTORE_COLLECTION`：任务集合名，默认 `apscheduler_jobs`
- `RUNS_COLLECTION`：执行记录集合名，默认 `job_runs`
- `SCHEDULER_TZ`：时区，默认 `Asia/Shanghai`
- `REQUEST_TIMEOUT`：任务请求超时时间（秒），默认 `10`

可参考 `.env.example`。

## 后续扩展（规划）

- 支持更多任务类型（例如脚本、消息队列等）
- 任务执行结果记录与追踪
- 简单权限控制（若将来对外开放）

## 目录结构

```
app/
  main.py
Dockerfile
requirements.txt
```
