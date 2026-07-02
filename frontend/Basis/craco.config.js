// Настройка сборки CRA без eject (react-scripts 5) через craco.
// Причина: на билдере Timeweb ограничена память — стандартная сборка падает с OOM
// («остановилось на build»), когда бандл вырос. Терсер-минификатор по умолчанию запускает
// параллельные воркеры, каждый держит копию AST в памяти → пик RAM превышает лимит билдера.
// Здесь отключаем параллелизм терсера и режем sourcemaps → пик памяти резко ниже,
// сборка укладывается в ограниченный билдер. На качество/размер бандла почти не влияет,
// только чуть дольше по времени (последовательная минификация).
const TerserPlugin = require("terser-webpack-plugin");

module.exports = {
  webpack: {
    configure: (webpackConfig, { env }) => {
      if (env === "production" && webpackConfig.optimization) {
        webpackConfig.optimization.minimizer = (webpackConfig.optimization.minimizer || []).map((plugin) => {
          if (plugin && plugin.constructor && plugin.constructor.name === "TerserPlugin") {
            return new TerserPlugin({
              parallel: false,                 // не плодить воркеры — главный источник пикового RAM
              terserOptions: (plugin.options && plugin.options.terserOptions) || {},
            });
          }
          return plugin;
        });
        webpackConfig.devtool = false;         // без sourcemaps в проде (память + размер)
        // scope hoisting (concatenateModules) склеивает модули в один — большой AST в памяти;
        // отключаем ради пика RAM (небольшой рост размера бандла приемлем на ограниченном билдере)
        webpackConfig.optimization.concatenateModules = false;
      }
      return webpackConfig;
    },
  },
};
