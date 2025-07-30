# Use an official Python runtime as a parent image. The 'slim' version is smaller.
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the file that lists the project's dependencies
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# --no-cache-dir makes the image smaller
# --upgrade pip ensures we have the latest version
RUN pip install --no-cache-dir --upgrade pip -r requirements.txt

# Copy the rest of your application's code into the container at /app
# This includes the 'api' and 'core' directories, and all .py files.
COPY . .

# Your docker-compose.yml file specifies the command to run,
# so we don't need a CMD or ENTRYPOINT here. The container will be built
# and ready to accept commands like 'uvicorn', 'celery worker', or 'celery beat'.