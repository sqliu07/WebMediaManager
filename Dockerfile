# 使用体积最小的 Python Alpine 版本
FROM python:3.11-alpine

# 设置工作目录
WORKDIR /app

# 安装基础依赖和 py7zr 所需组件（如有字幕下载功能）
RUN apk add --no-cache \
    bash \
    gcc \
    musl-dev \
    libffi-dev \
    zlib-dev \
    jpeg-dev \
    make \
    tzdata

# 设置中国时区（你可按自己需要修改）
ENV TZ=Asia/Shanghai

# 拷贝依赖文件
COPY requirements.txt ./

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝项目文件
COPY . /app

# 创建日志目录
RUN mkdir -p /app/log

# 设置 UTF-8 编码
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# 容器对外暴露端口
EXPOSE 8003

# 运行命令：使用多线程模式
CMD ["python", "app.py"]