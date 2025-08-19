#!/usr/bin/env python3
"""
Simple SQLite Database for Clinical Trial Matching Web App
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class TrialMatchingDB:
    """Simple SQLite database for storing trial matching data"""
    
    def __init__(self, db_path: str = "trial_matching.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create uploads table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS uploads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        trial_file TEXT NOT NULL,
                        patient_files TEXT NOT NULL,
                        status TEXT DEFAULT 'processing'
                    )
                ''')
                
                # Create results table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        upload_id INTEGER,
                        patient_filename TEXT NOT NULL,
                        trial_id TEXT NOT NULL,
                        trial_title TEXT NOT NULL,
                        eligible BOOLEAN NOT NULL,
                        score REAL NOT NULL,
                        matched_criteria TEXT,
                        unmatched_criteria TEXT,
                        missing_data TEXT,
                        exclusions TEXT,
                        suggested_tests TEXT,
                        explanation TEXT,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (upload_id) REFERENCES uploads (id)
                    )
                ''')
                
                # Create statistics table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS statistics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        total_uploads INTEGER DEFAULT 0,
                        total_patients INTEGER DEFAULT 0,
                        total_trials INTEGER DEFAULT 0,
                        successful_matches INTEGER DEFAULT 0,
                        last_updated TEXT NOT NULL
                    )
                ''')
                
                conn.commit()
                logger.info("Database initialized successfully")
                
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def save_upload(self, trial_file: str, patient_files: List[str]) -> int:
        """Save upload record and return upload ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO uploads (timestamp, trial_file, patient_files, status)
                    VALUES (?, ?, ?, ?)
                ''', (
                    datetime.now().isoformat(),
                    trial_file,
                    json.dumps(patient_files),
                    'completed'
                ))
                
                upload_id = cursor.lastrowid
                conn.commit()
                
                logger.info(f"Saved upload with ID: {upload_id}")
                return upload_id
                
        except Exception as e:
            logger.error(f"Error saving upload: {e}")
            raise
    
    def save_results(self, upload_id: int, results: List[Dict[str, Any]]):
        """Save matching results"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for patient_result in results:
                    patient_filename = patient_result['patient_filename']
                    
                    for trial in patient_result['ranked_trials']:
                        cursor.execute('''
                            INSERT INTO results (
                                upload_id, patient_filename, trial_id, trial_title,
                                eligible, score, matched_criteria, unmatched_criteria,
                                missing_data, exclusions, suggested_tests, explanation,
                                created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            upload_id,
                            patient_filename,
                            trial['trial_id'],
                            trial['trial_title'],
                            trial['result']['eligible'],
                            trial['result']['score'],
                            json.dumps(trial['result'].get('matched', [])),
                            json.dumps(trial['result'].get('unmatched', [])),
                            json.dumps(trial['result'].get('missing', [])),
                            json.dumps(trial['result'].get('exclusions_triggered', [])),
                            json.dumps(trial['result'].get('suggested_data', [])),
                            json.dumps(trial['explanation']),
                            datetime.now().isoformat()
                        ))
                
                conn.commit()
                logger.info(f"Saved results for upload ID: {upload_id}")
                
        except Exception as e:
            logger.error(f"Error saving results: {e}")
            raise
    
    def get_upload_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent upload history"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT id, timestamp, trial_file, patient_files, status
                    FROM uploads
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))
                
                uploads = []
                for row in cursor.fetchall():
                    uploads.append({
                        'id': row[0],
                        'timestamp': row[1],
                        'trial_file': row[2],
                        'patient_files': json.loads(row[3]),
                        'status': row[4]
                    })
                
                return uploads
                
        except Exception as e:
            logger.error(f"Error getting upload history: {e}")
            return []
    
    def get_results_by_upload(self, upload_id: int) -> List[Dict[str, Any]]:
        """Get results for a specific upload"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM results WHERE upload_id = ?
                    ORDER BY patient_filename, score DESC
                ''', (upload_id,))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'id': row[0],
                        'upload_id': row[1],
                        'patient_filename': row[2],
                        'trial_id': row[3],
                        'trial_title': row[4],
                        'eligible': bool(row[5]),
                        'score': row[6],
                        'matched_criteria': json.loads(row[7]) if row[7] else [],
                        'unmatched_criteria': json.loads(row[8]) if row[8] else [],
                        'missing_data': json.loads(row[9]) if row[9] else [],
                        'exclusions': json.loads(row[10]) if row[10] else [],
                        'suggested_tests': json.loads(row[11]) if row[11] else [],
                        'explanation': json.loads(row[12]) if row[12] else {},
                        'created_at': row[13]
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Error getting results: {e}")
            return []
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get upload count
                cursor.execute('SELECT COUNT(*) FROM uploads')
                total_uploads = cursor.fetchone()[0]
                
                # Get patient count
                cursor.execute('SELECT COUNT(DISTINCT patient_filename) FROM results')
                total_patients = cursor.fetchone()[0]
                
                # Get trial count
                cursor.execute('SELECT COUNT(DISTINCT trial_id) FROM results')
                total_trials = cursor.fetchone()[0]
                
                # Get successful matches
                cursor.execute('SELECT COUNT(*) FROM results WHERE eligible = 1')
                successful_matches = cursor.fetchone()[0]
                
                return {
                    'total_uploads': total_uploads,
                    'total_patients': total_patients,
                    'total_trials': total_trials,
                    'successful_matches': successful_matches,
                    'last_updated': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {
                'total_uploads': 0,
                'total_patients': 0,
                'total_trials': 0,
                'successful_matches': 0,
                'last_updated': datetime.now().isoformat()
            }

# Global database instance
db = TrialMatchingDB()
