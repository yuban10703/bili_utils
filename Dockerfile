FROM python:3.8.2-alpine

MAINTAINER yuban10703 "2846021566@qq.com"  

ENV LIBRARY_PATH=/lib:/usr/lib

WORKDIR /app

RUN apk add --no-cache --virtual bili git gcc build-base libffi-dev && \
	git clone https://github.com/yjqiang/bili_utils.git /app && \
	pip --no-cache-dir install aiohttp==3.6.2 rsa==4.0 toml==0.10.0 && \
	rm -r /var/cache/apk && \
	rm -r /usr/share/man && \
	apk del bili && \
	apk add --no-cache git

CMD git pull && \ 
	cd fetch_roomids/refresh_rooms_hub && \
	python run_distributed.py
    


  
