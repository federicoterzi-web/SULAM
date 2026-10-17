declare module "*.css";

declare module "*.jpg" {
  const url: string;
  export default url;
}
