docker build -t weizhi-crontask:latest .
docker rm -f weizhi-crontask
docker run -d \
  -p 8800:8800 \
  --restart always \
  --env-file .env \
  --name weizhi-crontask \
  --network rqk-net \
  weizhi-crontask:latest
docker logs -f weizhi-crontask