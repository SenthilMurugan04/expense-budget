
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator
import re


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr


class UserUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr


class UserResponse(BaseModel):
    id: int
    name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class CategoryResponse(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class BudgetCreate(BaseModel):
    user_id: int = Field(gt=0)
    category_id: int = Field(gt=0)
    amount: float = Field(gt=0, allow_inf_nan=False)
    month: str

    @field_validator("month")
    @classmethod
    def validate_month(cls, value):
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
            raise ValueError("Month must be in YYYY-MM format")
        return value


class BudgetUpdate(BaseModel):
    amount: float = Field(gt=0, allow_inf_nan=False)


class BudgetResponse(BaseModel):
    id: int
    user_id: int
    category_id: int
    amount: float
    month: str

    model_config = ConfigDict(from_attributes=True)


class ExpenseCreate(BaseModel):
    user_id: int = Field(gt=0)
    category_id: int = Field(gt=0)
    amount: float = Field(gt=0, allow_inf_nan=False)
    description: str = Field(min_length=1, max_length=255)
    expense_date: date


class ExpenseUpdate(BaseModel):
    category_id: int = Field(gt=0)
    amount: float = Field(gt=0, allow_inf_nan=False)
    description: str = Field(min_length=1, max_length=255)
    expense_date: date


class ExpenseResponse(BaseModel):
    id: int
    user_id: int
    category_id: int
    amount: float
    description: str
    expense_date: date

    model_config = ConfigDict(from_attributes=True)
