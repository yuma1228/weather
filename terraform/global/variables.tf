// global 層の変数はこれ1つだけに抑える。
// region は IAM がグローバルサービスで変わる余地がなく、project も固定値なので
// versions.tf にリテラルで書く。environments 側と変数が重複すると管理場所が増える。
variable "allowed_account_id" {
  type        = string
  description = "apply を許可する AWS アカウントID。public リポジトリに置かないため tfvars で渡す。"
}
