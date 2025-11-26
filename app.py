from flask import Flask, render_template, request, send_file, session, jsonify
import pandas as pd
import os
from scraper import scrape_nahdi
import uuid
import threading
import time

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Change this for production

# Global dictionary to store scraping job status
scraping_jobs = {}

def run_scraper(job_id, url, pause_event):
    def progress_callback(pages, products):
        if job_id in scraping_jobs:
            scraping_jobs[job_id]['pages'] = pages
            scraping_jobs[job_id]['products'] = products
            # Only update time if not paused
            if scraping_jobs[job_id]['status'] == 'running':
                scraping_jobs[job_id]['elapsed_time'] = int(time.time() - scraping_jobs[job_id]['start_time'])

    try:
        products, pages_count, products_count = scrape_nahdi(url, progress_callback, pause_event)
        
        if products is None:
            scraping_jobs[job_id]['status'] = 'failed'
            scraping_jobs[job_id]['error'] = 'Failed to initialize scraper'
            return

        # Save to a temporary CSV file
        filename = f"nahdi_products_{job_id}.csv"
        filepath = os.path.join('downloads', filename)
        os.makedirs('downloads', exist_ok=True)
        
        df = pd.DataFrame(products)
        df.to_csv(filepath, index=False)
        
        scraping_jobs[job_id]['status'] = 'completed'
        scraping_jobs[job_id]['filename'] = filename
        scraping_jobs[job_id]['pages'] = pages_count
        scraping_jobs[job_id]['products'] = products_count
        
    except Exception as e:
        scraping_jobs[job_id]['status'] = 'failed'
        scraping_jobs[job_id]['error'] = str(e)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'error': 'Please enter a URL'}), 400
    
    job_id = str(uuid.uuid4())
    pause_event = threading.Event()
    pause_event.set() # Start as running

    scraping_jobs[job_id] = {
        'status': 'running',
        'pages': 0,
        'products': 0,
        'start_time': time.time(),
        'elapsed_time': 0,
        'pause_event': pause_event
    }
    
    thread = threading.Thread(target=run_scraper, args=(job_id, url, pause_event))
    thread.start()
    
    return jsonify({'job_id': job_id})

@app.route('/pause/<job_id>', methods=['POST'])
def pause_job(job_id):
    job = scraping_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    if job['status'] == 'running':
        job['pause_event'].clear()
        job['status'] = 'paused'
        return jsonify({'status': 'paused'})
    
    return jsonify({'status': job['status']})

@app.route('/resume/<job_id>', methods=['POST'])
def resume_job(job_id):
    job = scraping_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    if job['status'] == 'paused':
        job['pause_event'].set()
        job['status'] = 'running'
        # Adjust start time to account for pause duration if needed, 
        # but for simple elapsed time display, we might just let it be or pause the counter.
        # For simplicity, we just resume.
        return jsonify({'status': 'running'})
    
    return jsonify({'status': job['status']})

@app.route('/status/<job_id>', methods=['GET'])
def status(job_id):
    job = scraping_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    # Update elapsed time for running jobs
    if job['status'] == 'running':
        job['elapsed_time'] = int(time.time() - job['start_time'])
    
    # Return a copy without the event object which is not serializable
    job_data = job.copy()
    if 'pause_event' in job_data:
        del job_data['pause_event']
        
    return jsonify(job_data)

@app.route('/result/<job_id>')
def result(job_id):
    job = scraping_jobs.get(job_id)
    if not job or job['status'] != 'completed':
        return "Job not found or not completed", 404
    
    # Store filename in session for download route
    session['filename'] = job['filename']
    return render_template('result.html', pages=job['pages'], products=job['products'], filename=job['filename'])

@app.route('/download')
def download():
    filename = session.get('filename')
    if not filename:
        return "No file generated", 400
    
    filepath = os.path.join('downloads', filename)
    if not os.path.exists(filepath):
        return "File not found", 404
        
    return send_file(filepath, as_attachment=True, download_name="nahdi_products.csv")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
