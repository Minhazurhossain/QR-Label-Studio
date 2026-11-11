import json
import sqlite3
from datetime import datetime


class Database:
    """SQLite persistence layer for PRAN Agro batch headers and drum QR details."""

    def __init__(self, db_name="pran_qr_system.db"):
        self.db_name = db_name
        self.conn = sqlite3.connect(db_name)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        # Batch Header Table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS batch_header (
                batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_no TEXT NOT NULL,
                item_name TEXT,
                product_type TEXT,
                plant_location TEXT,
                shift_code TEXT,
                quantity_kg REAL,
                created_by TEXT,
                created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'DRAFT'
            )
        ''')

        # Batch Detail Table (Per Drum)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS batch_detail (
                detail_id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER,
                drum_sl_no INTEGER NOT NULL,
                mfd DATE,
                exp DATE,
                shift_time TEXT,
                production_time TEXT,
                brix REAL,
                acidity REAL,
                ph_value REAL,
                evaporation_temp REAL,
                sterilization_temp REAL,
                filling_temp REAL,
                ascorbic_acid_ppm REAL,
                pasteurize_temp REAL,
                kms_ppm REAL,
                na_ms_ppm REAL,
                sb_ppm REAL,
                potassium_sorbet_ppm REAL,
                qr_data TEXT,
                print_status TEXT DEFAULT 'PENDING',
                printed_on TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES batch_header(batch_id)
            )
        ''')

        self.conn.commit()

    def add_batch_header(self, data):
        self.cursor.execute('''
            INSERT INTO batch_header (
                batch_no, item_name, product_type, plant_location,
                shift_code, quantity_kg, created_by, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['batch_no'],
            data.get('item_name'),
            data.get('product_type'),
            data.get('plant_location'),
            data.get('shift_code'),
            data.get('quantity_kg'),
            data.get('created_by', 'User'),
            data.get('status', 'DRAFT'),
        ))
        self.conn.commit()
        return self.cursor.lastrowid

    def _insert_drum_rows(self, batch_id, details_list, header_data=None):
        """Insert drum detail rows for a batch without committing."""
        for detail in details_list:
            qr_payload = detail.get('qr_data')
            if not qr_payload and header_data:
                qr_payload = json.dumps({
                    'batch': header_data.get('batch_no', ''),
                    'item': header_data.get('item_name', ''),
                    'drum': detail['drum_sl_no'],
                    'mfd': detail.get('mfd'),
                    'exp': detail.get('exp'),
                    'shift': detail.get('shift_time'),
                    'time': detail.get('production_time'),
                    'brix': detail.get('brix'),
                    'acidity': detail.get('acidity'),
                    'ph': detail.get('ph_value'),
                })

            self.cursor.execute('''
                INSERT INTO batch_detail (
                    batch_id, drum_sl_no, mfd, exp, shift_time,
                    production_time, brix, acidity, ph_value,
                    evaporation_temp, sterilization_temp, filling_temp,
                    ascorbic_acid_ppm, pasteurize_temp, kms_ppm, na_ms_ppm,
                    sb_ppm, potassium_sorbet_ppm, qr_data, print_status, printed_on
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                batch_id,
                detail['drum_sl_no'],
                detail.get('mfd'),
                detail.get('exp'),
                detail.get('shift_time'),
                detail.get('production_time'),
                detail.get('brix'),
                detail.get('acidity'),
                detail.get('ph_value'),
                detail.get('evaporation_temp'),
                detail.get('sterilization_temp'),
                detail.get('filling_temp'),
                detail.get('ascorbic_acid_ppm'),
                detail.get('pasteurize_temp'),
                detail.get('kms_ppm'),
                detail.get('na_ms_ppm'),
                detail.get('sb_ppm'),
                detail.get('potassium_sorbet_ppm'),
                qr_payload,
                detail.get('print_status', 'PENDING'),
                detail.get('printed_on'),
            ))

    def add_batch_detail(self, batch_id, details_list, header_data=None):
        self._insert_drum_rows(batch_id, details_list, header_data=header_data)
        self.conn.commit()

    def save_full_batch(self, header_data, details_list):
        """Atomically save a batch header and its drum details."""
        try:
            self.cursor.execute('''
                INSERT INTO batch_header (
                    batch_no, item_name, product_type, plant_location,
                    shift_code, quantity_kg, created_by, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                header_data['batch_no'],
                header_data.get('item_name'),
                header_data.get('product_type'),
                header_data.get('plant_location'),
                header_data.get('shift_code'),
                header_data.get('quantity_kg'),
                header_data.get('created_by', 'User'),
                header_data.get('status', 'DRAFT'),
            ))
            batch_id = self.cursor.lastrowid
            self._insert_drum_rows(batch_id, details_list, header_data=header_data)
            self.conn.commit()
            return batch_id
        except Exception:
            self.conn.rollback()
            raise

    def update_full_batch(self, batch_id, header_data, details_list):
        """Atomically update an existing batch header and replace its drum details."""
        try:
            self.cursor.execute('''
                UPDATE batch_header
                SET batch_no = ?, item_name = ?, product_type = ?,
                    plant_location = ?, shift_code = ?, quantity_kg = ?,
                    created_by = ?, status = ?
                WHERE batch_id = ?
            ''', (
                header_data['batch_no'],
                header_data.get('item_name'),
                header_data.get('product_type'),
                header_data.get('plant_location'),
                header_data.get('shift_code'),
                header_data.get('quantity_kg'),
                header_data.get('created_by', 'User'),
                header_data.get('status', 'DRAFT'),
                batch_id,
            ))
            self.cursor.execute("DELETE FROM batch_detail WHERE batch_id = ?", (batch_id,))
            self._insert_drum_rows(batch_id, details_list, header_data=header_data)
            self.conn.commit()
            return batch_id
        except Exception:
            self.conn.rollback()
            raise

    def get_batch_details(self, batch_id):
        self.cursor.execute('''
            SELECT h.batch_no, h.item_name, h.product_type, h.shift_code,
                   d.detail_id, d.drum_sl_no, d.mfd, d.exp, d.shift_time,
                   d.production_time, d.brix, d.acidity, d.ph_value,
                   d.evaporation_temp, d.sterilization_temp, d.filling_temp,
                   d.ascorbic_acid_ppm
            FROM batch_detail d
            JOIN batch_header h ON d.batch_id = h.batch_id
            WHERE d.batch_id = ?
            ORDER BY d.drum_sl_no, d.detail_id
        ''', (batch_id,))
        return self.cursor.fetchall()

    def get_batch_details_dicts(self, batch_id):
        """Return full batch + drum detail records as dictionaries."""
        cur = self.conn.cursor()
        cur.row_factory = sqlite3.Row
        cur.execute('''
            SELECT h.batch_id, h.batch_no, h.item_name, h.product_type,
                   h.plant_location, h.shift_code, h.quantity_kg,
                   h.created_by, h.created_on, h.status,
                   d.detail_id, d.drum_sl_no, d.mfd, d.exp, d.shift_time,
                   d.production_time, d.brix, d.acidity, d.ph_value,
                   d.evaporation_temp, d.sterilization_temp, d.filling_temp,
                   d.ascorbic_acid_ppm, d.pasteurize_temp, d.kms_ppm,
                   d.na_ms_ppm, d.sb_ppm, d.potassium_sorbet_ppm,
                   d.qr_data, d.print_status, d.printed_on
            FROM batch_detail d
            JOIN batch_header h ON d.batch_id = h.batch_id
            WHERE d.batch_id = ?
            ORDER BY d.drum_sl_no, d.detail_id
        ''', (batch_id,))
        return [dict(row) for row in cur.fetchall()]

    def get_batch_header(self, batch_id):
        cur = self.conn.cursor()
        cur.row_factory = sqlite3.Row
        cur.execute('''
            SELECT batch_id, batch_no, item_name, product_type, plant_location,
                   shift_code, quantity_kg, created_by, created_on, status
            FROM batch_header
            WHERE batch_id = ?
        ''', (batch_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_all_batches(self):
        self.cursor.execute('''
            SELECT batch_id, batch_no, item_name, created_on, status
            FROM batch_header
            ORDER BY created_on DESC
        ''')
        return self.cursor.fetchall()

    def get_batches_summary(self, search="", status_filter=None):
        """Return batches with drum counts and printed counts for the history view."""
        cur = self.conn.cursor()
        cur.row_factory = sqlite3.Row

        conditions = []
        params = []

        if search and search.strip():
            like = f"%{search.strip()}%"
            conditions.append(
                "(h.batch_no LIKE ? OR h.item_name LIKE ? OR h.plant_location LIKE ? OR h.product_type LIKE ?)"
            )
            params.extend([like, like, like, like])

        if status_filter and status_filter != "ALL":
            conditions.append("h.status = ?")
            params.append(status_filter)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cur.execute(f'''
            SELECT h.batch_id, h.batch_no, h.item_name, h.product_type,
                   h.plant_location, h.shift_code, h.quantity_kg,
                   h.created_by, h.created_on, h.status,
                   COUNT(d.detail_id) AS drum_count,
                   SUM(CASE WHEN d.print_status = 'PRINTED' THEN 1 ELSE 0 END) AS printed_count
            FROM batch_header h
            LEFT JOIN batch_detail d ON h.batch_id = d.batch_id
            {where_clause}
            GROUP BY h.batch_id
            ORDER BY h.created_on DESC, h.batch_id DESC
        ''', params)
        return [dict(row) for row in cur.fetchall()]

    def mark_batch_printed(self, batch_id, detail_ids=None):
        """Mark selected drums (or entire batch) as printed and update batch status."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if detail_ids:
            placeholders = ",".join("?" for _ in detail_ids)
            self.cursor.execute(
                f'''
                UPDATE batch_detail
                SET print_status = 'PRINTED', printed_on = ?
                WHERE batch_id = ? AND detail_id IN ({placeholders})
                ''',
                [now_str, batch_id, *detail_ids],
            )
        else:
            self.cursor.execute(
                '''
                UPDATE batch_detail
                SET print_status = 'PRINTED', printed_on = ?
                WHERE batch_id = ?
                ''',
                (now_str, batch_id),
            )

        self.cursor.execute(
            '''
            SELECT COUNT(*), SUM(CASE WHEN print_status = 'PRINTED' THEN 1 ELSE 0 END)
            FROM batch_detail
            WHERE batch_id = ?
            ''',
            (batch_id,),
        )
        total, printed = self.cursor.fetchone()
        printed = printed or 0
        if total > 0 and printed >= total:
            new_status = "PRINTED"
        elif printed > 0:
            new_status = "PARTIAL"
        else:
            new_status = "DRAFT"

        self.cursor.execute(
            "UPDATE batch_header SET status = ? WHERE batch_id = ?",
            (new_status, batch_id),
        )
        self.conn.commit()
        return new_status

    def delete_batch(self, batch_id):
        """Delete a batch and its associated drum details."""
        try:
            self.cursor.execute("DELETE FROM batch_detail WHERE batch_id = ?", (batch_id,))
            self.cursor.execute("DELETE FROM batch_header WHERE batch_id = ?", (batch_id,))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def get_dashboard_stats(self):
        """Return aggregate KPI counts for the UI header."""
        self.cursor.execute("SELECT COUNT(*) FROM batch_header")
        total_batches = self.cursor.fetchone()[0] or 0

        self.cursor.execute("SELECT COUNT(*) FROM batch_detail")
        total_drums = self.cursor.fetchone()[0] or 0

        self.cursor.execute("SELECT COUNT(*) FROM batch_detail WHERE print_status = 'PRINTED'")
        printed_drums = self.cursor.fetchone()[0] or 0

        self.cursor.execute("SELECT COUNT(*) FROM batch_header WHERE status = 'DRAFT'")
        draft_batches = self.cursor.fetchone()[0] or 0

        return {
            "total_batches": total_batches,
            "total_drums": total_drums,
            "printed_drums": printed_drums,
            "draft_batches": draft_batches,
        }

    def close(self):
        self.conn.close()
