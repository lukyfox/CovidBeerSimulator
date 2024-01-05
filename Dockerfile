# Use an official Python runtime as a parent image
FROM python:3.8

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy requirements.txt to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code to the working directory
COPY . .

# Run base simulation scenario with no infection and 1200 steps 
CMD ["python", "main.py", "-s no_covid", "-n 1200"]
