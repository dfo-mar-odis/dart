# This docker file is for testing various scenarios when runing DART

# Use the official Python image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    qtbase5-dev \
    libqt5gui5 \
    libqt5widgets5 \
    libqt5core5a

Run apt-get clean

RUN apt-get install -y git

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project files
COPY . .

# Expose the port the app runs on
EXPOSE 8007

# Run the application
CMD ["python", "manage.py", "dart", "-p", "8007"]