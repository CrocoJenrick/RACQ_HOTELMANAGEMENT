from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta
from db_config import get_db_connection
import traceback # Added for detailed error reporting

app = Flask(__name__)
app.secret_key = "your_secret_key"

# LOGIN SYSTEM WITHOUT ROLE COLUM
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# ONE LOGIN PAGE FOR ADMIN AND USER
@app.route("/", methods=["GET", "POST"])
def login():
    msg = ""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # ADMIN LOGIN CHECK
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["loggedin"] = True
            session["username"] = username
            session["role"] = "admin"
            return redirect(url_for("admin_dashboard"))

        # USER LOGIN CHECK
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
        user = cur.fetchone()

        cur.close()
        conn.close()

        if user:
            session["loggedin"] = True
            session["username"] = username
            session["role"] = "user"
            return redirect(url_for("user_dashboard"))
        else:
            msg = "Invalid account"

    # Check for external messages (like deletion success/failure)
    external_msg = request.args.get('msg')
    if external_msg:
        msg = external_msg

    return render_template("login.html", msg=msg)


# ONE REGISTER PAGE FOR USER ONLY
@app.route("/register", methods=["GET", "POST"])
def register():
    msg = ""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        name = request.form["name"]
        phone = request.form["phone"]
        email = request.form["email"]
        
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        exist = cur.fetchone()

        if exist:
            msg = "Username exists"
        else:
            cur.execute("INSERT INTO users (username, password) VALUES (%s,%s)", (username, password))
            conn.commit()
            
            # Login and redirect on successful registration
            session["loggedin"] = True
            session["username"] = username
            session["role"] = "user"
            
            cur.close()
            conn.close()
            return redirect(url_for("user_register_customer"))

        cur.close()
        conn.close()

    return render_template("register.html", msg=msg)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# DASHBOARDS
@app.route("/admin_dashboard")
def admin_dashboard():
    if "loggedin" not in session or session["role"] != "admin":
        return redirect(url_for("login"))
    return render_template("admin_dashboard.html", username=session["username"])

@app.route("/user_dashboard")
def user_dashboard():
    if "loggedin" not in session or session["role"] != "user":
        return redirect(url_for("login"))
    # Pass msg from flash or query parameters if needed later
    msg = request.args.get('msg', '') 
    return render_template("user_dashboard.html", username=session["username"], msg=msg)


# --- FIXED ROUTE FOR USER SELF-DELETION ---
@app.route("/user/delete_account", methods=["POST"])
def user_delete_account():
    if "loggedin" not in session or session["role"] != "user":
        return redirect(url_for("login"))

    username = session["username"]
    conn = get_db_connection()
    cur = conn.cursor()
    msg = "Account successfully deleted."

    try:
        # 1. Find customer_id linked to the username
        cur.execute("SELECT id FROM customers WHERE name=%s", (username,))
        customer_row = cur.fetchone()
        customer_id = customer_row[0] if customer_row else None
        
        # Start cleanup if a customer profile exists
        if customer_id:
            # 2. Get room IDs from active bookings to revert status
            cur.execute("SELECT room_id FROM bookings WHERE customer_id=%s", (customer_id,))
            booked_rooms = cur.fetchall()

            # 3. Delete related bookings
            cur.execute("DELETE FROM bookings WHERE customer_id=%s", (customer_id,))
            
            # 4. Delete related checkout history (CRUCIAL FIX!)
            cur.execute("DELETE FROM checkout_history WHERE customer_id=%s", (customer_id,))
            
            # 5. Update room statuses to 'Available' for deleted bookings
            for (room_id,) in booked_rooms:
                cur.execute("UPDATE rooms SET status='Available' WHERE id=%s", (room_id,))
                
            # 6. Delete customer profile
            cur.execute("DELETE FROM customers WHERE id=%s", (customer_id,))

        # 7. Delete user account
        cur.execute("DELETE FROM users WHERE username=%s", (username,))
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        # Log the full error to the console for debugging
        print("\n--- ERROR DURING USER ACCOUNT DELETION ---")
        traceback.print_exc()
        print("-------------------------------------------\n")
        msg = "Error deleting account. See server logs for details."
        
    finally:
        cur.close()
        conn.close()
        
    session.clear()
    return redirect(url_for("login", msg=msg))
# --- END FIXED ROUTE ---


# CUSTOMER REGISTRATION
@app.route("/register_customer", methods=["GET", "POST"])
def register_customer():
    if "loggedin" not in session or session["role"] != "admin":
        return redirect(url_for("login"))

    msg = ""
    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        email = request.form["email"]

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT * FROM customers WHERE name=%s OR phone=%s OR email=%s", (name, phone, email))
        existing = cur.fetchone()

        if existing:
            cur.execute("UPDATE customers SET name=%s, phone=%s, email=%s WHERE id=%s",
                         (name, phone, email, existing[0]))
            msg = "Customer updated"
        else:
            cur.execute("INSERT INTO customers (name, phone, email) VALUES (%s, %s, %s)",
                         (name, phone, email))
            msg = "Customer registered"

        conn.commit()
        cur.close()
        conn.close()

    return render_template("register_customer.html", msg=msg)

@app.route("/user/register_customer", methods=["GET", "POST"])
def user_register_customer():
    if "loggedin" not in session or session["role"] != "user":
        return redirect(url_for("login"))

    msg = ""

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        name = session["username"]
        phone = request.form["phone"]
        email = request.form["email"]

        cur.execute("SELECT * FROM customers WHERE name=%s", (name,))
        exist = cur.fetchone()

        if exist:
            cur.execute("UPDATE customers SET phone=%s, email=%s WHERE name=%s", (phone, email, name))
            msg = "Profile updated"
        else:
            cur.execute("INSERT INTO customers (name, phone, email) VALUES (%s,%s,%s)", (name, phone, email))
            msg = "Profile created"

        conn.commit()

    cur.execute("SELECT * FROM customers WHERE name=%s", (session["username"],))
    customer = cur.fetchone()

    cur.close()
    conn.close()

    return render_template("user_register_customer.html", customer=customer, msg=msg)

@app.route("/user/booking", methods=["GET", "POST"])
def user_booking():
    if "loggedin" not in session or session["role"] != "user":
        return redirect(url_for("login"))

    msg = ""
    conn = get_db_connection()
    cur = conn.cursor()

    action = request.form.get("_action")

    cur.execute("SELECT id FROM customers WHERE name=%s", (session["username"],))
    row = cur.fetchone()
    customer_id = row[0] if row else None

    if not customer_id:
        return render_template("user_booking.html", msg="Complete your customer profile first")

    if request.method == "POST":
        if action == "add":
            room_id = request.form["room_id"]
            checkin = request.form["checkin_date"]
            checkout = request.form["checkout_date"]
            total = request.form["total_amount"]

            cur.execute("INSERT INTO bookings (customer_id, room_id, checkin_date, checkout_date, total_amount) VALUES (%s,%s,%s,%s,%s)",
                        (customer_id, room_id, checkin, checkout, total))
            conn.commit()

            cur.execute("SELECT LAST_INSERT_ID()")
            bid = cur.fetchone()[0]
            session[f"user_booktime_{bid}"] = datetime.now().timestamp()

            cur.execute("UPDATE rooms SET status='Occupied' WHERE id=%s", (room_id,))
            conn.commit()

            msg = "Booked"

        if action == "update":
            bid = request.form["id"]

            saved = session.get(f"user_booktime_{bid}")
            if saved:
                old = datetime.fromtimestamp(saved)
                if datetime.now() - old > timedelta(minutes=3):
                    msg = "Edit expired"
                else:
                    room_id = request.form["room_id"]
                    checkin = request.form["checkin_date"]
                    checkout = request.form["checkout_date"]
                    total = request.form["total_amount"]

                    cur.execute("UPDATE bookings SET room_id=%s, checkin_date=%s, checkout_date=%s, total_amount=%s WHERE id=%s AND customer_id=%s",
                                 (room_id, checkin, checkout, total, bid, customer_id))
                    conn.commit()
                    msg = "Updated"

        if action == "delete":
            bid = request.form["id"]

            cur.execute("SELECT room_id FROM bookings WHERE id=%s AND customer_id=%s", (bid, customer_id))
            r = cur.fetchone()

            cur.execute("DELETE FROM bookings WHERE id=%s AND customer_id=%s", (bid, customer_id))
            conn.commit()

            if r:
                cur.execute("UPDATE rooms SET status='Available' WHERE id=%s", (r[0],))
                conn.commit()

            session.pop(f"user_booktime_{bid}", None)
            msg = "Canceled"

    cur.execute("SELECT id, room_number FROM rooms WHERE status='Available'")
    rooms = cur.fetchall()

    cur.execute("""SELECT b.id, r.room_number, b.checkin_date, b.checkout_date, b.total_amount
                    FROM bookings b JOIN rooms r ON b.room_id=r.id
                    WHERE b.customer_id=%s""", (customer_id,))
    bookings = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("user_booking.html", rooms=rooms, bookings=bookings, msg=msg)

@app.route("/view_customers")
def view_customers():
    if "loggedin" not in session or session["role"] != "admin":
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM customers")
    customers = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("view_customers.html", customers=customers)

#customers updates
@app.route("/edit_customer/<int:id>", methods=["GET", "POST"])
def edit_customer(id):
    if "loggedin" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        email = request.form["email"]

        cur.execute("UPDATE customers SET name=%s, phone=%s, email=%s WHERE id=%s", (name, phone, email, id))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for("view_customers"))

    cur.execute("SELECT * FROM customers WHERE id=%s", (id,))
    customer = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("edit_customer.html", customer=customer)

# --- FIXED ROUTE: Admin customer delete (Includes checkout_history cleanup) ---
@app.route("/delete_customer/<int:id>")
def delete_customer(id):
    if "loggedin" not in session or session["role"] != "admin":
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 1. Get customer name (which is used as the username)
        cur.execute("SELECT name FROM customers WHERE id=%s", (id,))
        customer_row = cur.fetchone()
        
        username = None
        if customer_row:
            username = customer_row[0]
            
            # 2. Get active bookings for the customer and update room status
            cur.execute("SELECT room_id FROM bookings WHERE customer_id=%s", (id,))
            booked_rooms = cur.fetchall()

            # 3. Delete related bookings
            cur.execute("DELETE FROM bookings WHERE customer_id=%s", (id,))
            
            # 4. Delete related checkout history (CRUCIAL FIX!)
            cur.execute("DELETE FROM checkout_history WHERE customer_id=%s", (id,))

            # 5. Update room status
            for (room_id,) in booked_rooms:
                cur.execute("UPDATE rooms SET status='Available' WHERE id=%s", (room_id,))
            
            # 6. Delete the customer profile
            cur.execute("DELETE FROM customers WHERE id=%s", (id,))
            
        # 7. Delete the user account associated with the customer name/username (if found)
        if username:
            cur.execute("DELETE FROM users WHERE username=%s", (username,))
            
        conn.commit()
            
    except Exception as e:
        conn.rollback()
        # Log the full error to the console for debugging
        print("\n--- ERROR DURING ADMIN CUSTOMER DELETION ---")
        traceback.print_exc()
        print("-------------------------------------------\n")
        
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("view_customers"))
# --- END FIXED ROUTE ---


# BOOKING SYSTEM
@app.route("/booking", methods=["GET", "POST"])
def booking():
    if "loggedin" not in session:
        return redirect(url_for("login"))

    msg = ""
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("_action")

        try:
            # ADD NEW BOOKING
            if action == "add":
                customer_id = request.form["customer_id"]
                room_id = request.form["room_id"]
                checkin = request.form["checkin_date"]
                checkout = request.form["checkout_date"]
                total = request.form["total_amount"]

                cur.execute(
                    "SELECT id FROM bookings WHERE room_id=%s AND checkin_date=%s AND checkout_date=%s",
                    (room_id, checkin, checkout),
                )
                existing = cur.fetchone()

                if existing:
                    msg = "Booking already exists for this room and date."
                else:
                    cur.execute(
                        "INSERT INTO bookings (customer_id, room_id, checkin_date, checkout_date, total_amount) VALUES (%s, %s, %s, %s, %s)",
                        (customer_id, room_id, checkin, checkout, total),
                    )
                    cur.execute("UPDATE rooms SET status='Occupied' WHERE id=%s", (room_id,))
                    conn.commit()
                    msg = "Booking added successfully."

            # UPDATE EXISTING BOOKING
            elif action == "update":
                booking_id = request.form["id"]
                customer_id = request.form["customer_id"]
                room_id = request.form["room_id"]
                checkin = request.form["checkin_date"]
                checkout = request.form["checkout_date"]
                total = request.form["total_amount"]

                cur.execute(
                    "UPDATE bookings SET customer_id=%s, room_id=%s, checkin_date=%s, checkout_date=%s, total_amount=%s WHERE id=%s",
                    (customer_id, room_id, checkin, checkout, total, booking_id),
                )
                conn.commit()
                msg = "Booking updated successfully."

            # DELETE BOOKING
            elif action == "delete":
                booking_id = request.form["id"]

                # Get room_id before deleting
                cur.execute("SELECT room_id FROM bookings WHERE id=%s", (booking_id,))
                room = cur.fetchone()

                # Delete booking
                cur.execute("DELETE FROM bookings WHERE id=%s", (booking_id,))
                conn.commit()

                # Update room status to 'Available'
                if room:
                    cur.execute("UPDATE rooms SET status='Available' WHERE id=%s", (room[0],))
                    conn.commit()

                msg = "Booking deleted successfully."

        except Exception as e:
            msg = f"Error processing booking: {e}"

    # Fetch customers, rooms, and bookings for display
    cur.execute("SELECT id, name FROM customers")
    customers = cur.fetchall()
    cur.execute("SELECT id, room_number FROM rooms")
    rooms = cur.fetchall()
    cur.execute(
        "SELECT b.id, c.name, r.room_number, b.checkin_date, b.checkout_date, b.total_amount FROM bookings b JOIN customers c ON b.customer_id=c.id JOIN rooms r ON b.room_id=r.id ORDER BY b.id ASC"
    )
    bookings = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("booking.html", customers=customers, rooms=rooms, bookings=bookings, msg=msg)


@app.route("/room_info", methods=["GET", "POST"])
def room_info():
    if "loggedin" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()
    msg = ""

    # --- Auto update room status based on bookings ---
    try:
        # 1. Mark rooms as occupied if they have active bookings
        cur.execute("""
            UPDATE rooms 
            SET status = 'Occupied'
            WHERE id IN (
                SELECT room_id FROM bookings
                WHERE CURDATE() BETWEEN checkin_date AND checkout_date
            )
        """)

        # 2. Mark rooms as available if their bookings ended
        cur.execute("""
            UPDATE rooms 
            SET status = 'Available'
            WHERE id NOT IN (
                SELECT room_id FROM bookings
                WHERE CURDATE() BETWEEN checkin_date AND checkout_date
            )
            AND status != 'Maintenance'
        """)

        conn.commit()
    except Exception as e:
        # This error handling is important if the database doesn't support CURDATE() or similar
        msg = f"Auto-update error: {e}"

    # --- Handle manual actions (Add, Delete, Update) ---
    if request.method == "POST":
        try:
            delete_id = request.form.get("delete_id")
            update_id = request.form.get("update_id")
            new_status = request.form.get("new_status")

            if delete_id:
                cur.execute("DELETE FROM rooms WHERE id=%s", (delete_id,))
                msg = "Room deleted successfully."
            elif update_id and new_status:
                cur.execute("UPDATE rooms SET status=%s WHERE id=%s", (new_status, update_id))
                msg = f"Room status updated to {new_status}."
            else:
                room_number = request.form["room_number"]
                room_type = request.form["room_type"]
                price = request.form["price"]
                status = request.form["status"]
                cur.execute(
                    "INSERT INTO rooms (room_number, room_type, price, status) VALUES (%s, %s, %s, %s)",
                    (room_number, room_type, price, status),
                )
                msg = "Room added successfully."
            conn.commit()
        except Exception as e:
            msg = f"Error processing request: {e}"

    # --- Fetch updated room data ---
    cur.execute("SELECT * FROM rooms")
    rooms = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM rooms")
    total_rooms = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM rooms WHERE status='Occupied'")
    occupied_count = cur.fetchone()[0]

    cur.close()
    conn.close()

    return render_template("room_info.html", rooms=rooms, msg=msg, total_rooms=total_rooms, occupied_count=occupied_count)

# CHECK-IN CHECK-OUT
@app.route("/checkin_checkout", methods=["GET", "POST"])
def checkin_checkout():
    if "loggedin" not in session or session["role"] != "admin":
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS checkout_history (
                    id INT PRIMARY KEY,
                    customer_id INT,
                    room_id INT,
                    checkin_date DATE,
                    checkout_date DATE,
                    total_amount DECIMAL(10,2)
                )""")
    conn.commit()

    if request.method == "POST":
        action = request.form["_action"]
        booking_id = request.form["id"]

        if action == "checkout":
            cur.execute("SELECT * FROM bookings WHERE id=%s", (booking_id,))
            row = cur.fetchone()

            if row:
                cur.execute("""INSERT INTO checkout_history 
                               (id, customer_id, room_id, checkin_date, checkout_date, total_amount)
                               VALUES (%s,%s,%s,%s,%s,%s)""",
                            (row[0], row[1], row[2], row[3], row[4], row[5]))

                cur.execute("UPDATE rooms SET status='Available' WHERE id=%s", (row[2],))
                cur.execute("DELETE FROM bookings WHERE id=%s", (booking_id,))
                conn.commit()

        elif action == "delete_history":
            cur.execute("DELETE FROM checkout_history WHERE id=%s", (booking_id,))
            conn.commit()

    cur.execute("""SELECT b.id, c.name, r.room_number, b.checkin_date, b.checkout_date, b.total_amount
                    FROM bookings b 
                    JOIN customers c ON b.customer_id=c.id 
                    JOIN rooms r ON b.room_id=r.id""")
    active = cur.fetchall()

    cur.execute("""SELECT h.id, c.name, r.room_number, h.checkin_date, h.checkout_date, h.total_amount
                    FROM checkout_history h 
                    JOIN customers c ON h.customer_id=c.id 
                    JOIN rooms r ON h.room_id=r.id""")
    history = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("checkin_checkout.html", active=active, history=history)

if __name__ == "__main__":
    app.run(debug=True)