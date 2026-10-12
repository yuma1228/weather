module "s3" {
  source             = "../../modules/s3"
  project            = var.project
  environment        = var.environment
  bucket_name        = var.bucket_name
  versioning_enabled = var.versioning_enabled
}

module "dynamodb" {
  source                         = "../../modules/dynamodb"
  project                        = var.project
  environment                    = var.environment
  table_name                     = var.table_name
  billing_mode                   = var.billing_mode
  hash_key                       = var.hash_key
  range_key                      = var.range_key
  read_capacity                  = var.read_capacity
  write_capacity                 = var.write_capacity
  deletion_protection            = var.deletion_protection
  ttl_attribute_name             = var.ttl_attribute_name
  ttl_enabled                    = var.ttl_enabled
  point_in_time_recovery_enabled = var.point_in_time_recovery_enabled
  server_side_encryption_enabled = var.server_side_encryption_enabled
}