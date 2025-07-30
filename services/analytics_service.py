import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import Session
from fastapi import HTTPException
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import IsolationForest
import uuid

from ..models.analytics import (
    AnalyticsMetric, RealtimeEvent, MLForecast, 
    AnomalyDetection, AnalyticsAuditLog, MetricType, TimeGranularity
)
from ..models.user import User
from ..models.shop import Shop
from ..database import get_db

logger = logging.getLogger(__name__)

class AnalyticsService:
    """
    Comprehensive analytics service with real-time capabilities,
    ML forecasting, and anomaly detection
    """
    
    def __init__(self):
        self.ml_models = {}
        self.anomaly_detectors = {}
        
    async def log_audit_event(
        self, 
        db: Session, 
        user_id: int, 
        user_role: str, 
        action: str, 
        resource: str,
        filters_applied: Dict = None,
        time_range: str = None,
        status: str = "success",
        error_message: str = None,
        ip_address: str = None,
        user_agent: str = None,
        request_id: str = None
    ):
        """Log analytics access for audit purposes"""
        try:
            audit_log = AnalyticsAuditLog(
                log_id=str(uuid.uuid4()),
                user_id=user_id,
                user_role=user_role,
                action=action,
                resource=resource,
                filters_applied=filters_applied or {},
                time_range=time_range,
                status=status,
                error_message=error_message,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id
            )
            db.add(audit_log)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to log audit event: {str(e)}")
    
    async def get_realtime_chart_data(
        self, 
        db: Session,
        metric_type: str,
        time_range: str = "24h",
        granularity: str = "hourly",
        shop_id: Optional[int] = None,
        category_id: Optional[int] = None,
        region: Optional[str] = None,
        user_id: int = None,
        user_role: str = None
    ) -> Dict[str, Any]:
        """
        Get real-time chart data with dynamic filtering
        """
        try:
            # Calculate time bounds
            now = datetime.utcnow()
            if time_range == "1h":
                start_time = now - timedelta(hours=1)
                granularity = "hourly"
            elif time_range == "24h":
                start_time = now - timedelta(hours=24)
                granularity = "hourly"
            elif time_range == "7d":
                start_time = now - timedelta(days=7)
                granularity = "daily"
            elif time_range == "30d":
                start_time = now - timedelta(days=30)
                granularity = "daily"
            elif time_range == "90d":
                start_time = now - timedelta(days=90)
                granularity = "daily"
            else:
                start_time = now - timedelta(days=30)
                granularity = "daily"
            
            # Build query with filters
            query = db.query(AnalyticsMetric).filter(
                and_(
                    AnalyticsMetric.metric_type == metric_type,
                    AnalyticsMetric.granularity == granularity,
                    AnalyticsMetric.timestamp >= start_time
                )
            )
            
            # Apply dimensional filters
            if shop_id:
                query = query.filter(AnalyticsMetric.shop_id == shop_id)
            if category_id:
                query = query.filter(AnalyticsMetric.category_id == category_id)
            if region:
                query = query.filter(AnalyticsMetric.region == region)
            
            # Get data points
            metrics = query.order_by(AnalyticsMetric.timestamp.asc()).all()
            
            # Format for charts
            chart_data = []
            for metric in metrics:
                chart_data.append({
                    "timestamp": metric.timestamp.isoformat(),
                    "date": metric.date_key,
                    "value": metric.value,
                    "count": metric.count,
                    "metadata": metric.metadata or {}
                })
            
            # Calculate aggregations
            total_value = sum(m.value for m in metrics)
            total_count = sum(m.count for m in metrics)
            avg_value = total_value / len(metrics) if metrics else 0
            
            # Get forecast if available
            forecast_data = await self.get_forecast_data(
                db, metric_type, granularity, shop_id, category_id, region
            )
            
            # Check for anomalies
            anomalies = await self.get_recent_anomalies(
                db, metric_type, shop_id, category_id, region
            )
            
            # Log access for audit
            if user_id:
                await self.log_audit_event(
                    db, user_id, user_role, "view_chart", f"{metric_type}_chart",
                    filters_applied={
                        "shop_id": shop_id, "category_id": category_id, 
                        "region": region, "time_range": time_range
                    },
                    time_range=time_range
                )
            
            return {
                "metric_type": metric_type,
                "time_range": time_range,
                "granularity": granularity,
                "data": chart_data,
                "aggregations": {
                    "total": total_value,
                    "count": total_count,
                    "average": avg_value,
                    "data_points": len(chart_data)
                },
                "forecast": forecast_data,
                "anomalies": anomalies,
                "filters": {
                    "shop_id": shop_id,
                    "category_id": category_id,
                    "region": region
                },
                "generated_at": now.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting chart data: {str(e)}")
            if user_id:
                await self.log_audit_event(
                    db, user_id, user_role, "view_chart", f"{metric_type}_chart",
                    status="failed", error_message=str(e)
                )
            raise HTTPException(status_code=500, detail="Failed to get chart data")
    
    async def process_realtime_event(self, db: Session, event_data: Dict[str, Any]):
        """
        Process real-time events and update analytics metrics
        """
        try:
            event_id = str(uuid.uuid4())
            
            # Create realtime event record
            realtime_event = RealtimeEvent(
                event_id=event_id,
                event_type=event_data.get("event_type"),
                entity_type=event_data.get("entity_type"),
                entity_id=event_data.get("entity_id"),
                data=event_data
            )
            db.add(realtime_event)
            
            # Update relevant analytics metrics
            await self._update_metrics_from_event(db, event_data)
            
            # Check for anomalies
            await self._detect_anomalies(db, event_data)
            
            # Mark event as processed
            realtime_event.processed = True
            realtime_event.processed_at = datetime.utcnow()
            
            db.commit()
            
            return {"event_id": event_id, "status": "processed"}
            
        except Exception as e:
            logger.error(f"Error processing realtime event: {str(e)}")
            db.rollback()
            raise
    
    async def _update_metrics_from_event(self, db: Session, event_data: Dict[str, Any]):
        """Update analytics metrics based on real-time events"""
        event_type = event_data.get("event_type")
        timestamp = datetime.utcnow()
        date_key = timestamp.strftime("%Y-%m-%d")
        hour_key = timestamp.strftime("%Y-%m-%d-%H")
        
        # Extract dimensional data
        shop_id = event_data.get("shop_id")
        category_id = event_data.get("category_id")
        region = event_data.get("region", "unknown")
        
        if event_type == "order_created":
            # Update order metrics
            await self._upsert_metric(
                db, "orders", "hourly", hour_key, 
                shop_id, category_id, region, 1, 1
            )
            await self._upsert_metric(
                db, "orders", "daily", date_key, 
                shop_id, category_id, region, 1, 1
            )
            
        elif event_type == "payment_completed":
            # Update revenue metrics
            amount = event_data.get("amount", 0)
            await self._upsert_metric(
                db, "revenue", "hourly", hour_key, 
                shop_id, category_id, region, amount, 1
            )
            await self._upsert_metric(
                db, "revenue", "daily", date_key, 
                shop_id, category_id, region, amount, 1
            )
            
        elif event_type == "user_registered":
            # Update user metrics
            await self._upsert_metric(
                db, "users", "hourly", hour_key, 
                None, None, region, 1, 1
            )
            await self._upsert_metric(
                db, "users", "daily", date_key, 
                None, None, region, 1, 1
            )
    
    async def _upsert_metric(
        self, db: Session, metric_type: str, granularity: str, 
        time_key: str, shop_id: Optional[int], category_id: Optional[int], 
        region: str, value: float, count: int
    ):
        """Upsert analytics metric (insert or update if exists)"""
        # Try to find existing metric
        existing = db.query(AnalyticsMetric).filter(
            and_(
                AnalyticsMetric.metric_type == metric_type,
                AnalyticsMetric.granularity == granularity,
                AnalyticsMetric.date_key == time_key if granularity == "daily" else AnalyticsMetric.hour_key == time_key,
                AnalyticsMetric.shop_id == shop_id,
                AnalyticsMetric.category_id == category_id,
                AnalyticsMetric.region == region
            )
        ).first()
        
        if existing:
            # Update existing metric
            existing.value += value
            existing.count += count
            existing.updated_at = datetime.utcnow()
        else:
            # Create new metric
            new_metric = AnalyticsMetric(
                metric_type=metric_type,
                granularity=granularity,
                date_key=time_key if granularity == "daily" else time_key[:10],
                hour_key=time_key if granularity == "hourly" else None,
                shop_id=shop_id,
                category_id=category_id,
                region=region,
                value=value,
                count=count
            )
            db.add(new_metric)
    
    async def generate_forecast(
        self, db: Session, metric_type: str, days_ahead: int = 7,
        shop_id: Optional[int] = None, category_id: Optional[int] = None,
        region: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate ML-based forecasts for metrics
        """
        try:
            # Get historical data (last 30 days)
            start_date = datetime.utcnow() - timedelta(days=30)
            
            query = db.query(AnalyticsMetric).filter(
                and_(
                    AnalyticsMetric.metric_type == metric_type,
                    AnalyticsMetric.granularity == "daily",
                    AnalyticsMetric.timestamp >= start_date
                )
            )
            
            # Apply filters
            if shop_id:
                query = query.filter(AnalyticsMetric.shop_id == shop_id)
            if category_id:
                query = query.filter(AnalyticsMetric.category_id == category_id)
            if region:
                query = query.filter(AnalyticsMetric.region == region)
            
            historical_data = query.order_by(AnalyticsMetric.timestamp.asc()).all()
            
            if len(historical_data) < 7:
                return []  # Not enough data for forecasting
            
            # Prepare data for ML model
            X = np.array(range(len(historical_data))).reshape(-1, 1)
            y = np.array([metric.value for metric in historical_data])
            
            # Train simple linear regression model
            model = LinearRegression()
            model.fit(X, y)
            
            # Generate forecasts
            forecasts = []
            for i in range(1, days_ahead + 1):
                future_x = np.array([[len(historical_data) + i - 1]])
                predicted_value = model.predict(future_x)[0]
                
                # Calculate confidence intervals (simplified)
                residuals = y - model.predict(X)
                std_error = np.std(residuals)
                confidence_lower = predicted_value - 1.96 * std_error
                confidence_upper = predicted_value + 1.96 * std_error
                
                forecast_date = datetime.utcnow() + timedelta(days=i)
                
                # Save forecast to database
                forecast = MLForecast(
                    forecast_id=str(uuid.uuid4()),
                    metric_type=metric_type,
                    forecast_date=forecast_date,
                    predicted_value=predicted_value,
                    confidence_lower=confidence_lower,
                    confidence_upper=confidence_upper,
                    model_name="linear_regression",
                    model_version="1.0",
                    shop_id=shop_id,
                    category_id=category_id,
                    region=region
                )
                db.add(forecast)
                
                forecasts.append({
                    "date": forecast_date.strftime("%Y-%m-%d"),
                    "predicted_value": predicted_value,
                    "confidence_lower": confidence_lower,
                    "confidence_upper": confidence_upper
                })
            
            db.commit()
            return forecasts
            
        except Exception as e:
            logger.error(f"Error generating forecast: {str(e)}")
            return []
    
    async def _detect_anomalies(self, db: Session, event_data: Dict[str, Any]):
        """
        Detect anomalies in real-time using ML models
        """
        try:
            metric_type = self._get_metric_type_from_event(event_data)
            if not metric_type:
                return
            
            # Get recent data for anomaly detection
            start_time = datetime.utcnow() - timedelta(hours=24)
            
            recent_metrics = db.query(AnalyticsMetric).filter(
                and_(
                    AnalyticsMetric.metric_type == metric_type,
                    AnalyticsMetric.granularity == "hourly",
                    AnalyticsMetric.timestamp >= start_time
                )
            ).order_by(AnalyticsMetric.timestamp.asc()).all()
            
            if len(recent_metrics) < 10:
                return  # Not enough data for anomaly detection
            
            # Prepare data for anomaly detection
            values = np.array([metric.value for metric in recent_metrics]).reshape(-1, 1)
            
            # Use Isolation Forest for anomaly detection
            detector = IsolationForest(contamination=0.1, random_state=42)
            anomaly_scores = detector.fit_predict(values)
            
            # Check if latest value is anomalous
            latest_score = anomaly_scores[-1]
            if latest_score == -1:  # Anomaly detected
                latest_metric = recent_metrics[-1]
                expected_value = np.mean([m.value for m in recent_metrics[:-1]])
                
                # Calculate severity based on deviation
                deviation = abs(latest_metric.value - expected_value) / expected_value if expected_value > 0 else 0
                if deviation > 0.5:
                    severity = "critical"
                elif deviation > 0.3:
                    severity = "high"
                elif deviation > 0.15:
                    severity = "medium"
                else:
                    severity = "low"
                
                # Save anomaly detection
                anomaly = AnomalyDetection(
                    detection_id=str(uuid.uuid4()),
                    metric_type=metric_type,
                    actual_value=latest_metric.value,
                    expected_value=expected_value,
                    anomaly_score=float(latest_score),
                    severity=severity,
                    algorithm="isolation_forest",
                    threshold=0.1,
                    shop_id=event_data.get("shop_id"),
                    category_id=event_data.get("category_id"),
                    region=event_data.get("region")
                )
                db.add(anomaly)
                
        except Exception as e:
            logger.error(f"Error detecting anomalies: {str(e)}")
    
    def _get_metric_type_from_event(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Map event type to metric type"""
        event_type = event_data.get("event_type")
        if event_type in ["order_created", "order_completed"]:
            return "orders"
        elif event_type in ["payment_completed", "payment_success"]:
            return "revenue"
        elif event_type == "user_registered":
            return "users"
        return None
    
    async def get_forecast_data(
        self, db: Session, metric_type: str, granularity: str,
        shop_id: Optional[int] = None, category_id: Optional[int] = None,
        region: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get existing forecast data"""
        try:
            query = db.query(MLForecast).filter(
                and_(
                    MLForecast.metric_type == metric_type,
                    MLForecast.forecast_date >= datetime.utcnow()
                )
            )
            
            if shop_id:
                query = query.filter(MLForecast.shop_id == shop_id)
            if category_id:
                query = query.filter(MLForecast.category_id == category_id)
            if region:
                query = query.filter(MLForecast.region == region)
            
            forecasts = query.order_by(MLForecast.forecast_date.asc()).limit(30).all()
            
            return [
                {
                    "date": f.forecast_date.strftime("%Y-%m-%d"),
                    "predicted_value": f.predicted_value,
                    "confidence_lower": f.confidence_lower,
                    "confidence_upper": f.confidence_upper,
                    "model": f.model_name
                }
                for f in forecasts
            ]
            
        except Exception as e:
            logger.error(f"Error getting forecast data: {str(e)}")
            return []
    
    async def get_recent_anomalies(
        self, db: Session, metric_type: str,
        shop_id: Optional[int] = None, category_id: Optional[int] = None,
        region: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent anomaly detections"""
        try:
            start_time = datetime.utcnow() - timedelta(hours=24)
            
            query = db.query(AnomalyDetection).filter(
                and_(
                    AnomalyDetection.metric_type == metric_type,
                    AnomalyDetection.timestamp >= start_time
                )
            )
            
            if shop_id:
                query = query.filter(AnomalyDetection.shop_id == shop_id)
            if category_id:
                query = query.filter(AnomalyDetection.category_id == category_id)
            if region:
                query = query.filter(AnomalyDetection.region == region)
            
            anomalies = query.order_by(AnomalyDetection.timestamp.desc()).limit(10).all()
            
            return [
                {
                    "timestamp": a.timestamp.isoformat(),
                    "actual_value": a.actual_value,
                    "expected_value": a.expected_value,
                    "severity": a.severity,
                    "anomaly_score": a.anomaly_score
                }
                for a in anomalies
            ]
            
        except Exception as e:
            logger.error(f"Error getting anomalies: {str(e)}")
            return []

# Global instance
analytics_service = AnalyticsService()