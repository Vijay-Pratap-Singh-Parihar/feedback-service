## Feedback Service

#### To build and start the application

```
docker-compose up --build
```

```
http://localhost:8001/docs
```

#### Check service health

```
GET /health
```

#### Get all ratings

```
GET /v1/ratings
```

#### Get specific rating

```
GET /v1/ratings/{rating_id}
```

#### Give rating about a trip
```
POST /v1/ratings
```