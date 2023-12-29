import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Updating the data for home page
    user_id = session["user_id"]
    # Updating the company and share table
    companies = db.execute("SELECT id, symbol, shares FROM shares JOIN company ON shares.company_id = company.id WHERE user_id = ?", user_id)
    for company in companies:
        response = lookup(company["symbol"])
        db.execute("UPDATE company SET price = ? WHERE symbol = ?", response["price"], company["symbol"])
        total = company["shares"] * response["price"]
        db.execute("UPDATE shares SET total = ? WHERE user_id = ? AND company_id = ?", total, user_id, company["id"])
    # Updating the grand_total column of users table
    rows_for_cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    rows_for_total = db.execute("SELECT SUM(total) AS total FROM shares WHERE user_id = ?", user_id)
    cash, total_amount_in_stocks = rows_for_cash[0]["cash"], rows_for_total[0]["total"]
    if total_amount_in_stocks is None:
        total_amount_in_stocks = 0
    grand_total = cash + total_amount_in_stocks
    db.execute("UPDATE users SET grand_total = ? WHERE id = ?", grand_total, user_id)

    # Retrieving data for home page
    rows_of_company = db.execute("SELECT symbol, name, shares, price, total FROM shares JOIN company ON shares.company_id = company.id WHERE user_id = ?", user_id)
    rows_of_users = db.execute("SELECT cash, grand_total FROM users WHERE id = ?", user_id)
    cash, grand_total = rows_of_users[0]["cash"], rows_of_users[0]["grand_total"]

    # Rendering index page
    return render_template("index.html", rows_of_company=rows_of_company, cash=cash, grand_total=grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Store symbol and shares in variables
        symbol = request.form.get("symbol")
        try:
            shares = int(request.form.get("shares")) if request.form.get("shares") else None
        except ValueError:
            return apology("invalid shares")

        # Use lookup function to send the request (for getting stock's quote)
        if symbol:
            if shares:
                if shares > 0:
                    response = lookup(symbol)
                else:
                    return apology("invalid shares")
            else:
                return apology("missing shares")
        else:
            return apology("missing symbol")

        # Checking for invalid symbol
        if not response:
            return apology("invalid symbol")

        # Checking if the user has enough cash
        rows_for_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        cash = rows_for_cash[0]["cash"]
        total_price_of_shares = response["price"] * shares
        if total_price_of_shares > cash:
            return apology("can't afford")

        # Storing name, symbol, price, and user_id in variables
        name, symbol, price, user_id = response["name"], response["symbol"], response["price"], session["user_id"]

        # Updating the company table
        rows_of_company = db.execute("SELECT * FROM company WHERE symbol = ?", symbol)
        if len(rows_of_company) == 0:
            db.execute("INSERT INTO company (name, symbol, price) VALUES (?, ?, ?)", name, symbol, price)
        else:
            db.execute("UPDATE company SET price = ? WHERE symbol = ?", price, symbol)

        # Storing company_id in variable
        rows_for_company_id = db.execute("SELECT id FROM company WHERE symbol = ?", symbol)
        company_id = rows_for_company_id[0]["id"]

        # Updating the history table
        db.execute("INSERT INTO history (user_id, symbol, shares, price, time) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)", user_id, symbol, shares, price)

        # Updating the shares table
        rows_of_shares = db.execute("SELECT * FROM shares WHERE user_id = ? AND company_id = ?", user_id, company_id)
        if len(rows_of_shares) == 0:
            db.execute("INSERT INTO shares (user_id, company_id, shares, total) VALUES (?, ?, ?, ?)", user_id, company_id, shares, total_price_of_shares)
        else:
            # Storing the updated shares and total_price_of_shares in variables
            rows_for_shares = db.execute("SELECT shares FROM shares WHERE user_id = ? AND company_id = ?", user_id, company_id)
            updated_shares = rows_for_shares[0]["shares"] + shares
            updated_total_price_of_shares = updated_shares * price
            # Updating the shares and total columns
            db.execute("UPDATE shares SET shares = ?, total = ? WHERE user_id = ? AND company_id = ?", updated_shares, updated_total_price_of_shares, user_id, company_id)

        # Updating the cash and grand_total columns of users table
        cash = cash - total_price_of_shares
        # Storing the grand_total in a variable
        rows_for_total = db.execute("SELECT SUM(total) AS total FROM shares WHERE user_id = ?", user_id)
        total_amount_in_stocks = rows_for_total[0]["total"]
        grand_total = cash + total_amount_in_stocks
        db.execute("UPDATE users SET cash = ?, grand_total = ? WHERE id = ?", cash, grand_total, user_id)

        # Redirecting user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    rows_of_history = db.execute("SELECT * FROM history WHERE user_id = ?", session["user_id"])
    return render_template("history.html", rows_of_history=rows_of_history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Store symbol in variable
        symbol = request.form.get("symbol")

        # Use lookup function to send the request (for getting stock's quote)
        if symbol:
            response = lookup(symbol)
        else:
            return apology("missing symbol")

        # Show user the stock's quote
        if response:
            return render_template("quoted.html", quote=response)
        else:
            return apology("invalid symbol")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Store username in variable
        username = request.form.get("username")

        # Ensure username was submitted
        if not username:
            return apology("must provide username")

        # Ensure username was unique
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(rows) > 0:
            return apology("username already exists")

        # Store password and confirmation in variables
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Ensure password was submitted
        if not password:
            return apology("missing password")

        # Ensure password and confirmation match
        if password != confirmation:
            return apology("passwords don't match")

        # Register the new user (store in the database users table)
        hash = generate_password_hash(password)
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash)

        # Remember which user has Registered
        user = db.execute("SELECT * FROM users WHERE username = ?", username)
        session["user_id"] = user[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Store symbol and shares in variables
        user_symbol = request.form.get("symbol")
        try:
            sold_shares = int(request.form.get("shares")) if request.form.get("shares") else None
        except ValueError:
            return apology("invalid shares")

        # Storing user_id  in a variable
        user_id = session["user_id"]

        # Server side validation for making sure that the user provided right data
        if user_symbol:
            response = lookup(user_symbol)
            if not response:
                return apology("invalid symbol")
            # Storing name, symbol, price in variables
            name, symbol, price = response["name"], response["symbol"], response["price"]
            rows = db.execute("SELECT id, shares FROM shares JOIN company ON shares.company_id = company.id WHERE user_id = ? AND symbol = ?", user_id, symbol)
            if len(rows) == 0:
                return apology("symbol not owned")
            # Storing company_id, current_shares in variables
            company_id = rows[0]["id"]
            current_shares = rows[0]["shares"]
            if not sold_shares:
                return apology("missing shares")
            if not sold_shares > 0:
                    return apology("invalid shares")
            if current_shares < sold_shares:
                return apology("too many shares")
        else:
            return apology("missing symbol")

        # Updating the shares and total columns of the shares table
        updated_shares = current_shares - sold_shares
        if updated_shares < 1:
            db.execute("DELETE FROM shares WHERE user_id = ? AND company_id = ?", user_id, company_id)
        else:
            updated_total_price_of_shares = updated_shares * price
            db.execute("UPDATE shares SET shares = ?, total = ? WHERE user_id = ? AND company_id = ?", updated_shares, updated_total_price_of_shares, user_id, company_id)

        # Updating cash, grand_total columns of users table
        rows_for_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        cash = rows_for_cash[0]["cash"]
        total_price_of_sold_shares = sold_shares * price
        cash = cash + total_price_of_sold_shares
        rows_for_total = db.execute("SELECT SUM(total) AS total FROM shares WHERE user_id = ?", user_id)
        total_amount_in_stocks = rows_for_total[0]["total"]
        if total_amount_in_stocks is None:
            total_amount_in_stocks = 0
        grand_total = cash + total_amount_in_stocks
        db.execute("UPDATE users SET cash = ?, grand_total = ? WHERE id = ?", cash, grand_total, user_id)

        # Updatig the history table
        db.execute("INSERT INTO history (user_id, symbol, shares, price, time) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)", user_id, symbol, -sold_shares, price)

        # Redirecting user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        rows_for_symbols = db.execute("SELECT symbol FROM shares JOIN company ON shares.company_id = company.id WHERE user_id = ?", session["user_id"])
        return render_template("sell.html", rows_for_symbols=rows_for_symbols)


@app.route("/cash", methods=["GET", "POST"])
@login_required
def cash():
    """Allow user to add more cash to their account"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Server side validation for making sure that the user provided right data
        try:
            add_cash = int(request.form.get("cash")) if request.form.get("cash") else None
        except ValueError:
            return apology("invalid cash")

        if not add_cash:
            return apology("missing cash")

        if not add_cash > 0:
            return apology("invalid cash")

        # Updating the cash column of users table
        user_id = session["user_id"]
        rows_for_cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        current_cash = rows_for_cash[0]["cash"]
        updated_cash = current_cash + add_cash
        db.execute("UPDATE users SET cash = ? WHERE id = ?", updated_cash, user_id)

        # Redirecting user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("cash.html")
