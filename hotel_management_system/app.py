from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta
from db_config import get_db_connection

app = Flask(__name__)
app.secret_key = "your_secret_key"

# LOGIN SYSTEM WITHOUT ROLE COLUM
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

@app.route("/home")
def home():
    return render_template("home.html")

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

        if user:
            session["loggedin"] = True
            session["username"] = username
            session["role"] = "user"
            session["user_id"] = user[0]  # store user_id in session

            # try to load linked customer profile (if any)
            cur.execute("SELECT * FROM customers WHERE user_id=%s LIMIT 1", (user[0],))
            cust = cur.fetchone()
            if cust:
                session["customer_id"] = cust[0]
                # assume cursor returns dict-like row or index 1 is name depending on your cursor setup
                session["full_name"] = cust.get("name") if isinstance(cust, dict) else cust[1]
            else:
                session["full_name"] = username

            cur.close()
            conn.close()
            return redirect(url_for("user_dashboard"))
        else:
            msg = "Invalid account"

        cur.close()
        conn.close()

    return render_template("login.html", msg=msg)


# ONE REGISTER PAGE FOR USER ONLY
@app.route("/register", methods=["GET", "POST"])
def register():
    msg = ""
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()

        conn = get_db_connection()
        cur = conn.cursor()

        # check existing username
        cur.execute("SELECT id FROM users WHERE username=%s", (username,))
        if cur.fetchone():
            msg = "Username already exists"
        else:
            # insert user
            cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
            conn.commit()
            user_id = cur.lastrowid

            # insert customer profile linked to this user (no schema change required)
            # if your customers table doesn't have user_id column, remove that field and just insert name/phone/email
            # below assumes customers has no user_id column; if you have user_id, include it accordingly.
            try:
                # try inserting with user_id column first (if exists)
                cur.execute("INSERT INTO customers (name, phone, email, user_id) VALUES (%s, %s, %s, %s)",
                            (name, phone, email, user_id))
            except Exception:
                # fallback: insert without user_id
                cur.execute("INSERT INTO customers (name, phone, email) VALUES (%s, %s, %s)",
                            (name, phone, email))
            conn.commit()
            customer_id = cur.lastrowid

            # set session so profile and booking shows the full name immediately
            session["loggedin"] = True
            session["username"] = username
            session["role"] = "user"
            session["user_id"] = user_id
            session["customer_id"] = customer_id
            session["full_name"] = name
            session["phone"] = phone
            session["email"] = email

            cur.close()
            conn.close()
            return redirect(url_for("user_dashboard"))

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
        return redirect(url_for("admin_login"))
    return render_template("admin_dashboard.html", username=session["username"])

@app.route("/user_dashboard")
def user_dashboard():
    if "loggedin" not in session or session["role"] != "user":
        return redirect(url_for("user_login"))
    return render_template("user_dashboard.html", username=session["username"])

# CUSTOMER REGISTRATION
@app.route("/register_customer", methods=["GET", "POST"])
def register_customer():
    if "loggedin" not in session or session["role"] != "admin":
        return redirect(url_for("admin_login"))

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
    if "loggedin" not in session or session.get("role") != "user":
        return redirect(url_for("login"))

    msg = ""
    conn = get_db_connection()
    cur = conn.cursor()

    # try to resolve customer id (prefer session)
    customer_id = session.get("customer_id")
    if not customer_id:
        # fallback: try to find customer by user_id if available
        user_id = session.get("user_id")
        if user_id:
            cur.execute("SELECT id, name, phone, email FROM customers WHERE user_id=%s LIMIT 1", (user_id,))
            row = cur.fetchone()
            if row:
                customer_id = row[0]
                session["customer_id"] = customer_id

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()

        if customer_id:
            cur.execute("UPDATE customers SET name=%s, phone=%s, email=%s WHERE id=%s",
                        (name, phone, email, customer_id))
            conn.commit()
            msg = "Profile updated"
        else:
            cur.execute("INSERT INTO customers (name, phone, email) VALUES (%s, %s, %s)",
                        (name, phone, email))
            conn.commit()
            customer_id = cur.lastrowid
            session["customer_id"] = customer_id
            msg = "Profile created"

        # refresh session values used in UI
        session["full_name"] = name
        session["phone"] = phone
        session["email"] = email

    # load customer to prefill form
    customer = None
    if customer_id:
        cur.execute("SELECT id, name, phone, email FROM customers WHERE id=%s", (customer_id,))
        customer = cur.fetchone()  # tuple: (id, name, phone, email)

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

    # Resolve customer_id reliably:
    customer_id = session.get("customer_id")
    if not customer_id:
        # try by linked user_id
        user_id = session.get("user_id")
        if user_id:
            cur.execute("SELECT id FROM customers WHERE user_id=%s LIMIT 1", (user_id,))
            row = cur.fetchone()
            if row:
                customer_id = row[0]
                session["customer_id"] = customer_id

    if not customer_id:
        # try by full name (fallback)
        name_lookup = session.get("full_name") or session.get("username")
        cur.execute("SELECT id FROM customers WHERE name=%s LIMIT 1", (name_lookup,))
        row = cur.fetchone()
        if row:
            customer_id = row[0]
            session["customer_id"] = customer_id

    # If still no customer profile, render page but prompt user to complete profile
    if not customer_id:
        cur.execute("SELECT id, room_number FROM rooms WHERE status='Available'")
        rooms = cur.fetchall()
        cur.close()
        conn.close()
        return render_template("user_booking.html", rooms=rooms, bookings=[], msg="Complete your customer profile first")

    # --- existing booking logic (add/update/delete) ---
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

        elif action == "update":
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

        elif action == "delete":
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

    # fetch available rooms and this customer's bookings
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
        return redirect(url_for("admin_login"))

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

#customer delete
@app.route("/delete_customer/<int:id>")
def delete_customer(id):
    if "loggedin" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1) Free any rooms held by this customer's active bookings
        cur.execute("SELECT room_id FROM bookings WHERE customer_id=%s", (id,))
        rooms = cur.fetchall()
        for r in rooms:
            cur.execute("UPDATE rooms SET status='Available' WHERE id=%s", (r[0],))

        # 2) Delete bookings for this customer
        cur.execute("DELETE FROM bookings WHERE customer_id=%s", (id,))

        # 3) Delete checkout history for this customer (if any)
        cur.execute("DELETE FROM checkout_history WHERE customer_id=%s", (id,))

        # 4) Now delete the customer
        cur.execute("DELETE FROM customers WHERE id=%s", (id,))

        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        # You can adjust the error handling (flash/message) as needed
        return redirect(url_for("view_customers"))
    cur.close()
    conn.close()
    return redirect(url_for("view_customers"))

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
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Auto-checkout overdue bookings: move to checkout_history, free room, delete booking
        cur.execute("""
            SELECT id, customer_id, room_id, checkin_date, checkout_date, total_amount
            FROM bookings
            WHERE checkout_date < CURDATE()
        """)
        overdue = cur.fetchall()
        for bid, cust_id, room_id, checkin_date, checkout_date, total_amount in overdue:
            # Insert with computed id (no schema change). Uses MAX(id)+1 from checkout_history.
            cur.execute("""
                INSERT INTO checkout_history (id, customer_id, room_id, checkin_date, checkout_date, total_amount)
                SELECT IFNULL(MAX(id),0)+1, %s, %s, %s, %s, %s FROM checkout_history
            """, (cust_id, room_id, checkin_date, checkout_date, total_amount))
            cur.execute("UPDATE rooms SET status='Available' WHERE id=%s", (room_id,))
            cur.execute("DELETE FROM bookings WHERE id=%s", (bid,))
        conn.commit()

        # Handle manual POST actions (checkout or delete history)
        if request.method == "POST":
            action = request.form.get("_action")
            if action == "checkout":
                bid = request.form.get("id")
                cur.execute("SELECT customer_id, room_id, checkin_date, checkout_date, total_amount FROM bookings WHERE id=%s", (bid,))
                row = cur.fetchone()
                if row:
                    cust_id, room_id, checkin_date, checkout_date, total_amount = row
                    cur.execute("""
                        INSERT INTO checkout_history (id, customer_id, room_id, checkin_date, checkout_date, total_amount)
                        SELECT IFNULL(MAX(id),0)+1, %s, %s, %s, %s, %s FROM checkout_history
                    """, (cust_id, room_id, checkin_date, checkout_date, total_amount))
                    cur.execute("DELETE FROM bookings WHERE id=%s", (bid,))
                    cur.execute("UPDATE rooms SET status='Available' WHERE id=%s", (room_id,))
                    conn.commit()
            elif action == "delete_history":
                hid = request.form.get("id")
                cur.execute("DELETE FROM checkout_history WHERE id=%s", (hid,))
                conn.commit()

        # Load active bookings (checkout_date >= today)
        cur.execute("""
            SELECT b.id, c.name, r.room_number, b.checkin_date, b.checkout_date, b.total_amount
            FROM bookings b
            JOIN customers c ON b.customer_id = c.id
            JOIN rooms r ON b.room_id = r.id
            WHERE b.checkout_date >= CURDATE()
            ORDER BY b.id
        """)
        active = cur.fetchall()

        cur.execute("""
            SELECT h.id, c.name, r.room_number, h.checkin_date, h.checkout_date, h.total_amount
            FROM checkout_history h
            JOIN customers c ON h.customer_id = c.id
            JOIN rooms r ON h.room_id = r.id
            ORDER BY h.id DESC
        """)
        history = cur.fetchall()

    finally:
        cur.close()
        conn.close()

    return render_template("checkin_checkout.html", active=active, history=history)

if __name__ == "__main__":
    app.run(debug=True)