module "s3" {
  source             = "../../modules/s3"
  project            = var.project
  environment        = var.environment
  bucket_name        = var.bucket_name
  versioning_enabled = var.versioning_enabled
}
