
from datetime import date
from calendar import monthrange

from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

import models
import schemas
from database import engine, get_db

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Smart Expense & Budget Alert API",
    description="Manage expenses, monthly budgets and budget alerts",
    version="1.0.0"
)


# --------------------------------------------------
# COMMON FUNCTIONS
# --------------------------------------------------

def check_user(db, user_id):
    user = db.query(models.User).filter(
        models.User.id == user_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


def check_category(db, category_id):
    category = db.query(models.Category).filter(
        models.Category.id == category_id
    ).first()

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    return category


def get_budget_status(budget, expense):
    if budget <= 0:
        return "NO_BUDGET"

    usage = (expense / budget) * 100

    if usage < 70:
        return "SAFE"
    elif usage < 100:
        return "WARNING"
    else:
        return "EXCEEDED"


def get_category_spending(db, user_id, category_id, month):
    total = db.query(
        func.coalesce(func.sum(models.Expense.amount), 0)
    ).filter(
        models.Expense.user_id == user_id,
        models.Expense.category_id == category_id,
        func.strftime("%Y-%m", models.Expense.expense_date) == month
    ).scalar()

    return float(total)


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.get("/")
def home():
    return {"message": "Smart Expense & Budget Alert API is running"}


# --------------------------------------------------
# 1. USER MANAGEMENT
# --------------------------------------------------

@app.post("/users", response_model=schemas.UserResponse, status_code=201)
def create_user(data: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(
        models.User.email == str(data.email)
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    user = models.User(
        name=data.name,
        email=str(data.email)
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@app.get("/users", response_model=list[schemas.UserResponse])
def get_users(db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.id).all()


@app.get("/users/{user_id}", response_model=schemas.UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    return check_user(db, user_id)


@app.put("/users/{user_id}", response_model=schemas.UserResponse)
def update_user(
    user_id: int,
    data: schemas.UserUpdate,
    db: Session = Depends(get_db)
):
    user = check_user(db, user_id)

    existing = db.query(models.User).filter(
        models.User.email == str(data.email),
        models.User.id != user_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    user.name = data.name
    user.email = str(data.email)

    db.commit()
    db.refresh(user)

    return user


@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = check_user(db, user_id)

    # Delete related records first
    db.query(models.Expense).filter(
        models.Expense.user_id == user_id
    ).delete(synchronize_session=False)

    db.query(models.Budget).filter(
        models.Budget.user_id == user_id
    ).delete(synchronize_session=False)

    db.delete(user)
    db.commit()

    return {"message": "User and related records deleted successfully"}


# --------------------------------------------------
# 2. CATEGORY MANAGEMENT
# --------------------------------------------------

@app.post("/categories", response_model=schemas.CategoryResponse, status_code=201)
def add_category(data: schemas.CategoryCreate, db: Session = Depends(get_db)):
    name = data.name.strip()

    if not name:
        raise HTTPException(status_code=400, detail="Category name is required")

    existing = db.query(models.Category).filter(
        func.lower(models.Category.name) == name.lower()
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Category already exists")

    category = models.Category(name=name)
    db.add(category)
    db.commit()
    db.refresh(category)

    return category


@app.get("/categories", response_model=list[schemas.CategoryResponse])
def list_categories(db: Session = Depends(get_db)):
    return db.query(models.Category).order_by(models.Category.name).all()


# --------------------------------------------------
# 3. BUDGET MANAGEMENT
# --------------------------------------------------

@app.post("/budgets", response_model=schemas.BudgetResponse, status_code=201)
def create_budget(data: schemas.BudgetCreate, db: Session = Depends(get_db)):
    check_user(db, data.user_id)
    check_category(db, data.category_id)

    existing = db.query(models.Budget).filter(
        models.Budget.user_id == data.user_id,
        models.Budget.category_id == data.category_id,
        models.Budget.month == data.month
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Budget already exists for this category and month. Use PUT to update it."
        )

    budget = models.Budget(
        user_id=data.user_id,
        category_id=data.category_id,
        amount=data.amount,
        month=data.month
    )

    db.add(budget)
    db.commit()
    db.refresh(budget)

    return budget


@app.get("/users/{user_id}/budgets")
def get_user_budgets(
    user_id: int,
    month: str = Query(default_factory=lambda: date.today().strftime("%Y-%m")),
    db: Session = Depends(get_db)
):
    check_user(db, user_id)

    budgets = db.query(
        models.Budget,
        models.Category.name.label("category_name")
    ).join(
        models.Category,
        models.Budget.category_id == models.Category.id
    ).filter(
        models.Budget.user_id == user_id,
        models.Budget.month == month
    ).order_by(models.Category.name).all()

    result = []

    for budget, category_name in budgets:
        spent = get_category_spending(
            db, user_id, budget.category_id, month
        )

        result.append({
            "budget_id": budget.id,
            "category_id": budget.category_id,
            "category": category_name,
            "month": month,
            "budget": budget.amount,
            "expense": spent,
            "remaining": round(budget.amount - spent, 2),
            "status": get_budget_status(budget.amount, spent)
        })

    return result


@app.put("/budgets/{budget_id}", response_model=schemas.BudgetResponse)
def update_budget(
    budget_id: int,
    data: schemas.BudgetUpdate,
    db: Session = Depends(get_db)
):
    budget = db.query(models.Budget).filter(
        models.Budget.id == budget_id
    ).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    budget.amount = data.amount
    db.commit()
    db.refresh(budget)

    return budget


# --------------------------------------------------
# 4. EXPENSE MANAGEMENT + BUDGET ALERT
# --------------------------------------------------

@app.post("/expenses", status_code=201)
def add_expense(data: schemas.ExpenseCreate, db: Session = Depends(get_db)):
    check_user(db, data.user_id)
    category = check_category(db, data.category_id)

    expense = models.Expense(
        user_id=data.user_id,
        category_id=data.category_id,
        amount=data.amount,
        description=data.description.strip(),
        expense_date=data.expense_date
    )

    if not expense.description:
        raise HTTPException(status_code=400, detail="Description is required")

    db.add(expense)
    db.commit()
    db.refresh(expense)

    month = data.expense_date.strftime("%Y-%m")

    budget = db.query(models.Budget).filter(
        models.Budget.user_id == data.user_id,
        models.Budget.category_id == data.category_id,
        models.Budget.month == month
    ).first()

    if budget:
        spent = get_category_spending(
            db, data.user_id, data.category_id, month
        )
        usage = (spent / budget.amount) * 100

        return {
            "message": "Expense added successfully",
            "expense": {
                "id": expense.id,
                "user_id": expense.user_id,
                "category_id": expense.category_id,
                "category": category.name,
                "amount": expense.amount,
                "description": expense.description,
                "expense_date": str(expense.expense_date)
            },
            "budget": budget.amount,
            "total_category_expense": round(spent, 2),
            "remaining_budget": round(budget.amount - spent, 2),
            "usage_percentage": round(usage, 2),
            "status": get_budget_status(budget.amount, spent)
        }

    return {
        "message": "Expense added successfully",
        "expense_id": expense.id,
        "category": category.name,
        "status": "NO_BUDGET",
        "note": f"No budget was set for {month} in this category"
    }


@app.get("/expenses", response_model=list[schemas.ExpenseResponse])
def get_expenses(
    user_id: int | None = None,
    category_id: int | None = None,
    month: str | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Expense)

    if user_id is not None:
        check_user(db, user_id)
        query = query.filter(models.Expense.user_id == user_id)

    if category_id is not None:
        check_category(db, category_id)
        query = query.filter(models.Expense.category_id == category_id)

    if month is not None:
        try:
            date.fromisoformat(month + "-01")
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Month must be in YYYY-MM format"
            )

        if len(month) != 7:
            raise HTTPException(
                status_code=400,
                detail="Month must be in YYYY-MM format"
            )

        query = query.filter(
            func.strftime("%Y-%m", models.Expense.expense_date) == month
        )

    return query.order_by(models.Expense.expense_date.desc()).all()


@app.get("/expenses/{expense_id}", response_model=schemas.ExpenseResponse)
def get_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.query(models.Expense).filter(
        models.Expense.id == expense_id
    ).first()

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    return expense


@app.put("/expenses/{expense_id}")
def update_expense(
    expense_id: int,
    data: schemas.ExpenseUpdate,
    db: Session = Depends(get_db)
):
    expense = db.query(models.Expense).filter(
        models.Expense.id == expense_id
    ).first()

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    check_category(db, data.category_id)

    expense.category_id = data.category_id
    expense.amount = data.amount
    expense.description = data.description.strip()
    expense.expense_date = data.expense_date

    if not expense.description:
        raise HTTPException(status_code=400, detail="Description is required")

    db.commit()
    db.refresh(expense)

    month = expense.expense_date.strftime("%Y-%m")

    budget = db.query(models.Budget).filter(
        models.Budget.user_id == expense.user_id,
        models.Budget.category_id == expense.category_id,
        models.Budget.month == month
    ).first()

    result = {
        "message": "Expense updated successfully",
        "expense": {
            "id": expense.id,
            "user_id": expense.user_id,
            "category_id": expense.category_id,
            "amount": expense.amount,
            "description": expense.description,
            "expense_date": str(expense.expense_date)
        }
    }

    if budget:
        spent = get_category_spending(
            db, expense.user_id, expense.category_id, month
        )
        result["budget"] = budget.amount
        result["total_category_expense"] = round(spent, 2)
        result["remaining_budget"] = round(budget.amount - spent, 2)
        result["status"] = get_budget_status(budget.amount, spent)
    else:
        result["status"] = "NO_BUDGET"

    return result


@app.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.query(models.Expense).filter(
        models.Expense.id == expense_id
    ).first()

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    db.delete(expense)
    db.commit()

    return {"message": "Expense deleted successfully"}


# --------------------------------------------------
# 5. EXPENSE SUMMARY
# --------------------------------------------------

@app.get("/users/{user_id}/expense-summary")
def expense_summary(
    user_id: int,
    month: str = Query(default_factory=lambda: date.today().strftime("%Y-%m")),
    db: Session = Depends(get_db)
):
    check_user(db, user_id)

    # JOIN categories and budgets
    rows = db.query(
        models.Category.id,
        models.Category.name,
        func.coalesce(models.Budget.amount, 0).label("budget"),
        func.coalesce(func.sum(models.Expense.amount), 0).label("expense")
    ).outerjoin(
        models.Budget,
        (models.Budget.category_id == models.Category.id)
        & (models.Budget.user_id == user_id)
        & (models.Budget.month == month)
    ).outerjoin(
        models.Expense,
        (models.Expense.category_id == models.Category.id)
        & (models.Expense.user_id == user_id)
        & (func.strftime("%Y-%m", models.Expense.expense_date) == month)
    ).group_by(
        models.Category.id,
        models.Category.name,
        models.Budget.amount
    ).order_by(models.Category.name).all()

    categories = []
    total_budget = 0.0
    total_expense = 0.0

    for row in rows:
        budget_amount = float(row.budget)
        expense_amount = float(row.expense)

        categories.append({
            "category_id": row.id,
            "category": row.name,
            "budget": round(budget_amount, 2),
            "expense": round(expense_amount, 2),
            "remaining": round(budget_amount - expense_amount, 2),
            "status": get_budget_status(budget_amount, expense_amount)
        })

        total_budget += budget_amount
        total_expense += expense_amount

    return {
        "user_id": user_id,
        "month": month,
        "total_budget": round(total_budget, 2),
        "total_expense": round(total_expense, 2),
        "remaining_budget": round(total_budget - total_expense, 2),
        "categories": categories
    }


# --------------------------------------------------
# 6. BONUS: TOP 5 EXPENSES
# --------------------------------------------------

@app.get("/users/{user_id}/top-expenses")
def top_expenses(user_id: int, db: Session = Depends(get_db)):
    check_user(db, user_id)

    rows = db.query(
        models.Expense,
        models.Category.name.label("category_name")
    ).join(
        models.Category,
        models.Expense.category_id == models.Category.id
    ).filter(
        models.Expense.user_id == user_id
    ).order_by(
        models.Expense.amount.desc(),
        models.Expense.id
    ).limit(5).all()

    return [
        {
            "id": expense.id,
            "category": category_name,
            "amount": expense.amount,
            "description": expense.description,
            "expense_date": str(expense.expense_date)
        }
        for expense, category_name in rows
    ]


# --------------------------------------------------
# 7. BONUS: MONTHLY SPENDING SUMMARY
# --------------------------------------------------

@app.get("/users/{user_id}/monthly-summary")
def monthly_summary(user_id: int, db: Session = Depends(get_db)):
    check_user(db, user_id)

    rows = db.query(
        func.strftime("%Y-%m", models.Expense.expense_date).label("month"),
        func.sum(models.Expense.amount).label("total_expense")
    ).filter(
        models.Expense.user_id == user_id
    ).group_by(
        func.strftime("%Y-%m", models.Expense.expense_date)
    ).order_by(
        func.strftime("%Y-%m", models.Expense.expense_date).desc()
    ).all()

    return [
        {
            "month": row.month,
            "total_expense": round(float(row.total_expense), 2)
        }
        for row in rows
    ]


# --------------------------------------------------
# CREATE DEFAULT CATEGORIES
# --------------------------------------------------

@app.on_event("startup")
def create_default_categories():
    db = next(get_db())

    try:
        default_categories = [
            "Food",
            "Travel",
            "Shopping",
            "Bills",
            "Entertainment",
            "Others"
        ]

        for name in default_categories:
            existing = db.query(models.Category).filter(
                func.lower(models.Category.name) == name.lower()
            ).first()

            if not existing:
                db.add(models.Category(name=name))

        db.commit()
    finally:
        db.close()
