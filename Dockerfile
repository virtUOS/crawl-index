# Use the official Python image from Docker Hub
FROM python:3.11

# Set the working directory
WORKDIR /app



# Install dependencies
RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt


# Copy the project
COPY . .


# Add the src directory to PYTHONPATH
# ENV PYTHONPATH=/app/

# # Set the environment variable for Scrapy settings
# ENV SCRAPY_SETTINGS_MODULE=src.crawler.settings

# EXPOSE 6800
# Default command 
# CMD ["scrapy", "shell"]



