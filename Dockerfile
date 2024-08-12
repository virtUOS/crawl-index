# Use the official Python image from Docker Hub
FROM python:3.11

# Set the working directory
WORKDIR /app

# Copy the project
COPY . .


# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt


# Set the environment variable for Scrapy settings
ENV SCRAPY_SETTINGS_MODULE=crawler.settings

# The default command is a bash shell to prevent auto-crawling
CMD ["bash"]



